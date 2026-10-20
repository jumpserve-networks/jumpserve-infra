// Install through DevTools in the existing authenticated production tab.
// Observe real fetches; never mock identity, API responses or Storage transport.
// Credentials remain in browser memory and are never returned in evidence.
() => {
  const original = window.fetch.bind(window);
  const state = { events: [], requests: {}, storage: null };
  const api = "https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/paper-uploads";
  const safe = value => ({ version: value.version, id: value.id, status: value.status, result_id: value.result?.id, sha256: value.sha256, byte_count: value.byte_count });
  window.fetch = async (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url);
    const relevant = request.url === api;
    let action;
    if (relevant) {
      action = JSON.parse(await request.clone().text()).action;
      state.requests[action] = request.clone();
    }
    const response = await original(input, init);
    if (relevant) state.events.push({ type: "authenticated-api", action, http_status: response.status, response: safe(await response.clone().json()) });
    if (url.hostname === "regphejnlvfpyokpniny.supabase.co" && url.pathname.includes("/object/upload/sign/research-paper-uploads/")) {
      state.storage = request.clone();
      state.events.push({ type: "real-signed-storage-upload", method: request.method, http_status: response.status, path: url.pathname });
    }
    return response;
  };
  state.replay = async () => {
    const results = [];
    for (const action of ["reserve", "start"]) {
      if (!state.requests[action]) throw Error("Original authenticated request not recorded");
      const response = await original(state.requests[action].clone());
      results.push({ action, http_status: response.status, response: safe(await response.json()) });
    }
    state.events.push({ type: "same-request-id-replay", results });
    return results;
  };
  state.privateRead = async () => {
    if (!state.storage || !state.requests.start) throw Error("Actual owner upload required first");
    const signed = new URL(state.storage.url);
    const url = signed.origin + signed.pathname.replace("/object/upload/sign/", "/object/");
    const response = await original(url, { headers: { apikey: state.storage.headers.get("apikey"), Authorization: state.requests.start.headers.get("Authorization") } });
    const result = { type: "normal-authenticated-private-storage-read", http_status: response.status, denied: [400, 401, 403, 404].includes(response.status) };
    state.events.push(result);
    return result;
  };
  window.__paperReleaseControl = state;
  return { installed: true, credentials_exported: false, responses_mocked: false };
}
