"""Bound model retries for a selector with no mutation or network-launch tools."""
from strands.hooks.events import BeforeModelCallEvent
class IPv6Limits:
    def __init__(self):self.calls=0
    def register_hooks(self,registry,**kwargs):registry.add_callback(BeforeModelCallEvent,self.before)
    def before(self,event):
        self.calls+=1
        if self.calls>2:event.cancel='IPv6 study model-call limit reached'
