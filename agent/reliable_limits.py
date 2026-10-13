"""Bound model retries/cycles; no arbitrary tools are offered to the selector."""
from strands.hooks.events import BeforeModelCallEvent
class ReliableLimits:
    def __init__(self):self.calls=0
    def register_hooks(self,registry,**kwargs):registry.add_callback(BeforeModelCallEvent,self.before)
    def before(self,event):
        self.calls+=1
        if self.calls>2:event.cancel='ReliableSketch model-call limit reached'
