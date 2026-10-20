"""Local actual API/controller/SQL/arithmetic with explicit synthetic boundaries."""
import base64,json,os,threading,time,urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import check_research_ideas_database as f
import autonomy,autonomy_model as model,worker,paper_uploads
import autonomy_fixtures as fixture

f.bootstrap();f.rpc('publish_agent_prompt',fixture.publish_fixture())
fixture.preparation.registered=fixture.registered;model.invoke=fixture.provider
os.environ.update(RESEARCH_AUTONOMY_ENABLED='true',RESEARCH_QUEUE_WORKERS_ENABLED='true')
stop=threading.Event()
def background():
 while not stop.wait(.3):
  try:
   # Shortened polling only, never model/SQL semantics. Timing is not scientific.
   f.query("update research_autonomy_tasks set next_at=clock_timestamp() where status='waiting'")
   autonomy.handler({})
   for _ in range(2):
    job=f.rpc('research_queue_claim',dict(p_worker=f.uid()))
    if job:worker.execute_job(job)
  except Exception as error:print(json.dumps(dict(fixture_background_error=type(error).__name__)),flush=True)
threading.Thread(target=background,daemon=True).start()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def respond(self,status,value):
  raw=json.dumps(value).encode();self.send_response(status)
  for key,value in {'Content-Type':'application/json','Content-Length':str(len(raw)),'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'authorization,content-type,accept,x-upload-token','Access-Control-Allow-Methods':'GET,POST,PUT,OPTIONS','Cache-Control':'no-store'}.items():self.send_header(key,value)
  self.end_headers();self.wfile.write(raw)
 def do_OPTIONS(self):self.respond(200,{})
 def do_GET(self):self.handle_request('GET')
 def do_POST(self):self.handle_request('POST')
 def do_PUT(self):
  try:
   if self.headers.get('Authorization')!='Bearer explicit-software-fixture' or self.headers.get('X-Upload-Token')!='explicit-local-upload-permission':return self.respond(401,dict(error='Explicit local upload permission required'))
   path=urllib.parse.urlsplit(self.path).path
   if not path.startswith('/fixture-paper-upload/'):return self.respond(404,dict(error='Not a fixture upload route'))
   identity=path.removeprefix('/fixture-paper-upload/');study,sha=identity.split('/')
   upload=paper_uploads.owned(f.ACTOR,study)
   if upload['paper']['paper_upload']['sha256']!=sha:return self.respond(403,dict(error='Different reserved PDF'))
   length=int(self.headers.get('Content-Length',0))
   if not 1<=length<=paper_uploads.MAX_BYTES:return self.respond(413,dict(error='PDF fixture byte limit'))
   f.transport('/storage/v1/object/'+paper_uploads.BUCKET+'/'+identity,'POST',self.rfile.read(length));self.respond(200,dict(stored=True,synthetic_storage=True))
  except Exception as error:self.respond(409 if 'HTTP 409' in str(error) else 400,dict(error=str(error)))
 def handle_request(self,method):
  parsed=urllib.parse.urlsplit(self.path)
  if parsed.path=='/fixture-metadata':return self.respond(200,dict(database=f.DATABASE,url=fixture.URL,pdf_base64=base64.b64encode(fixture.pdf_bytes()).decode(),synthetic_auth=True,synthetic_provider=True,synthetic_storage=True,actual_cloud=False))
  if self.headers.get('Authorization')!='Bearer explicit-software-fixture':return self.respond(401,dict(error='Explicit synthetic local authentication required.'))
  try:
   raw=self.rfile.read(int(self.headers.get('Content-Length',0))).decode() if method=='POST' else None
   event=dict(rawPath=parsed.path,body=raw,requestContext=dict(http=dict(method=method)),queryStringParameters=dict(urllib.parse.parse_qsl(parsed.query)))
   self.respond(200,f.api.dispatch(event,f.ACTOR))
  except Exception as error:self.respond(getattr(error,'status',400),dict(error=str(error)))
print(json.dumps(dict(port=4104,database=f.DATABASE,synthetic_auth=True,synthetic_provider=True,synthetic_storage=True)),flush=True)
try:ThreadingHTTPServer(('127.0.0.1',4104),Handler).serve_forever()
finally:stop.set()
