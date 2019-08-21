import logging
from aiozmq import rpc

from ai.backend.common.logging import BraceStyleAdapter

log = BraceStyleAdapter(logging.getLogger('ai.backend.storage.server'))

async def run(cmd: str) -> List[str]:
    proc = await create_subprocess_shell(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = await proc.communicate()

    return out.decode(), err.decode() if err else ''


class AbstractVolumeAgent:
    async def init(self): 
        pass
    
    async def create(self, kernel_id: str, size: int):
        pass

    async def remove(self, kernel_id: str):
        pass


class AgentRPCServer(rpc.AttrHandler):
    def __init__(self):
        self.agent: AbstractVolumeAgent = None
    
    async def init(self, mode: str, **kwargs):
        if mode == 'xfs':
            from .xfs.agent import VolumeAgent
            self.agent = VolumeAgent(kwargs['mount_path'])
        elif mode == 'btrfs':
            # TODO: Implement Btrfs Agent
        await self.agent.init()

        rpc_addr = '127.0.0.1:12321'
        agent_addr = f"tcp://{rpc_addr}"
        self.rpc_server = await rpc.serve_rpc(self, bind=agent_addr)
        self.rpc_server.transport.setsockopt(zmq.LINGER, 200)

    @rpc.method
    async def create(self, kernel_id: str, size: int):
        return await self.agent.create(kernel_id, size)
    
    @rpc.method
    async def remove(self, kernel_id: str):
        return await self.agent.remove(kernel_id)
