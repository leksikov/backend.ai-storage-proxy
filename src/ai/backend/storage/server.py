import logging
import os
from pprint import pformat, pprint
from setproctitle import setproctitle
import sys

import aiotools
from aiozmq import rpc
import click
import trafaret as t

from ai.backend.common import config
from ai.backend.common.logging import BraceStyleAdapter
from ai.backend.common import validators as tx

from . import __version__ as VERSION

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
    def __init__(self, config):
        self.config = config

        self.agent: AbstractVolumeAgent = None
    
    async def init(self):
        if self.config['storage']['mode'] == 'xfs':
            from .xfs.agent import VolumeAgent
            self.agent = VolumeAgent(kwargs['mount_path'])
        elif self.config['storage']['mode'] == 'btrfs':
            # TODO: Implement Btrfs Agent
        await self.agent.init()

        rpc_addr = self.config['agent']['rpc-listen-addr']
        agent_addr = f"tcp://{rpc_addr}"
        self.rpc_server = await rpc.serve_rpc(self, bind=agent_addr)
        self.rpc_server.transport.setsockopt(zmq.LINGER, 200)

    @aiotools.actxmgr
    async def handle_rpc_exception(self):
        try:
            yield
        except AssertionError:
            log.exception('assertion failure')
            raise
        except Exception:
            log.exception('unexpected error')
            raise
    
    @rpc.method
    async def create(self, kernel_id: str, size: int):
        log.debug('rpc::create({0}, {1})', kernel_id, size)
        async with self.handle_rpc_exception():
            return await self.agent.create(kernel_id, size)    
    
    @rpc.method
    async def remove(self, kernel_id: str):
        log.debug('rpc::remove({0})', kernel_id)
        async with self.handle_rpc_exception():
            return await self.agent.remove(kernel_id)


@aiotools.server
async def server_main(loop, config):
    agent = AgentRPCServer(config, loop=loop)
    await agent.init()


@click.group(invoke_without_command=True)
@click.option('-f', '--config-path', '--config', type=Path, default=None,
              help='The config file path. (default: ./volume.toml and /etc/backend.ai/volume.toml)')
@click.option('--debug', is_flag=True,
              help='Enable the debug mode and override the global log level to DEBUG.')
def main():
    volume_config_iv = t.Dict({
        t.Key('agent'): t.Dict({
            t.Key('mode'): t.Enum('scratch', 'vfolder'),
            t.Key('rpc-listen-addr'): tx.HostPortPair(allow_blank_host=True),
            t.Key('event-loop', default='asyncio'): t.Enum('asyncio', 'uvloop')
        }),
        t.Key('storage'): t.Dict({
            t.Key('mode'): t.Enum('xfs', 'btrfs'),
            t.Key('path'): t.String
        })
    }).allow_extra('*')

    # Determine where to read configuration.
    raw_cfg, cfg_src_path = config.read_from_file(config_path, 'agent')

    try:
        cfg = config.check(raw_cfg, volume_config_iv)
        cfg['_src'] = cfg_src_path
    except config.ConfigurationError as e:
        print('ConfigurationError: Validation of agent configuration has failed:', file=sys.stderr)
        print(pformat(e.invalid_data), file=sys.stderr)
        raise click.Abort()

    rpc_host = cfg['agent']['rpc-listen-addr'].host
    if (isinstance(rpc_host, BaseIPAddress) and
        (rpc_host.is_unspecified or rpc_host.is_link_local)):
        print('ConfigurationError: '
              'Cannot use link-local or unspecified IP address as the RPC listening host.',
              file=sys.stderr)
        raise click.Abort()

    if os.getuid() != 0:
        print('Storage agent can only be run as root', file=sys.stderr)
        raise click.Abort()

    if cli_ctx.invoked_subcommand is None:
        logger = Logger(cfg['logging'])
        setproctitle('Backend.AI: Storage Agent')
        log.info('Backend.AI Storage Agent', VERSION)

        log_config = logging.getLogger('ai.backend.agent.config')
        if debug:
            log_config.debug('debug mode enabled.')
        
        if cfg['agent']['event-loop'] == 'uvloop':
            uvloop.install()
            log.info('Using uvloop as the event loop backend')
        aiotools.start_server(server_main, num_workers=1,
                                use_threading=True, args=(cfg, ))
        log.info('exit.')
    return 0

if __name__ == "__main__":
    sys.exit(main())