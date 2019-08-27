from asyncio import subprocess, create_subprocess_shell
from ipaddress import _BaseAddress as BaseIPAddress
import logging
import os
from pathlib import Path
from pprint import pformat, pprint
from setproctitle import setproctitle
import sys
from typing import List

import aiotools
from aiozmq import rpc
import click
import trafaret as t
import zmq

from ai.backend.common import config
from ai.backend.common.etcd import AsyncEtcd, ConfigScopes
from ai.backend.common.logging import Logger, BraceStyleAdapter
from ai.backend.common import validators as tx

from . import __version__ as VERSION
from .exception import ExecutionError

log = BraceStyleAdapter(logging.getLogger('ai.backend.storage.server'))


async def run(cmd: str) -> List[str]:
    log.debug('Executing [{}]', cmd)
    proc = await create_subprocess_shell(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = await proc.communicate()

    if err:
        raise ExecutionError(err.decode())
    
    return out.decode()


class AbstractVolumeAgent:
    async def init(self):
        pass

    async def create(self, kernel_id: str, size: str):
        pass

    async def remove(self, kernel_id: str):
        pass

    async def get(self, kernel_id: str):
        pass


class AgentRPCServer(rpc.AttrHandler):
    def __init__(self, etcd, config):
        self.config = config
        self.etcd = etcd

        self.agent: AbstractVolumeAgent = None

    async def init(self):
        await self.update_status('starting')

        if self.config['storage']['mode'] == 'xfs':
            from .xfs.agent import VolumeAgent
            self.agent = VolumeAgent(
                self.config['storage']['path'],
                self.config['agent']['user-uid'],
                self.config['agent']['user-gid']
            )
        elif self.config['storage']['mode'] == 'btrfs':
            # TODO: Implement Btrfs Agent
            pass
        await self.agent.init()

        rpc_addr = self.config['agent']['rpc-listen-addr']
        agent_addr = f"tcp://{rpc_addr}"
        self.rpc_server = await rpc.serve_rpc(self, bind=agent_addr)
        self.rpc_server.transport.setsockopt(zmq.LINGER, 200)
        log.info('started handling RPC requests at {}', rpc_addr)

        await self.etcd.put('ip', rpc_addr.host, scope=ConfigScopes.NODE)
        await self.update_status('running')

    async def shutdown(self):
        if self.rpc_server is not None:
            self.rpc_server.close()
            await self.rpc_server.wait_closed()

    async def update_status(self, status):
        await self.etcd.put('', status, scope=ConfigScopes.NODE)

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
    async def hello(self, agent_id: str) -> str:
        log.debug('rpc::hello({0})', agent_id)
        return 'OLLEH'

    @rpc.method
    async def create(self, kernel_id: str, size: str) -> str:
        log.debug('rpc::create({0}, {1})', kernel_id, size)
        async with self.handle_rpc_exception():
            return await self.agent.create(kernel_id, size)

    @rpc.method
    async def remove(self, kernel_id: str):
        log.debug('rpc::remove({0})', kernel_id)
        async with self.handle_rpc_exception():
            return await self.agent.remove(kernel_id)

    @rpc.method
    async def get(self, kernel_id: str) -> str:
        log.debug('rpc::get({0})', kernel_id)
        async with self.handle_rpc_exception():
            return await self.agent.get(kernel_id)


@aiotools.server
async def server_main(loop, pidx, _args):
    config = _args[0]

    etcd_credentials = None
    if config['etcd']['user']:
        etcd_credentials = {
            'user': config['etcd']['user'],
            'password': config['etcd']['password'],
        }
    scope_prefix_map = {
        ConfigScopes.GLOBAL: '',
        ConfigScopes.NODE: 'nodes/storage',
    }
    etcd = AsyncEtcd(config['etcd']['addr'],
                     config['etcd']['namespace'],
                     scope_prefix_map,
                     credentials=etcd_credentials)

    agent = AgentRPCServer(etcd, config)
    await agent.init()
    try:
        yield
    finally:
        log.info('Shutting down...')
        await agent.shutdown()


@click.group(invoke_without_command=True)
@click.option('-f', '--config-path', '--config', type=Path, default=None,
              help='The config file path. (default: ./volume.toml and /etc/backend.ai/volume.toml)')
@click.option('--debug', is_flag=True,
              help='Enable the debug mode and override the global log level to DEBUG.')
@click.pass_context
def main(cli_ctx, config_path, debug):
    volume_config_iv = t.Dict({
        t.Key('etcd'): t.Dict({
            t.Key('namespace'): t.String,
            t.Key('addr'): tx.HostPortPair(allow_blank_host=False)
        }).allow_extra('*'),
        t.Key('logging'): t.Any,  # checked in ai.backend.common.logging
        t.Key('agent'): t.Dict({
            t.Key('mode'): t.Enum('scratch', 'vfolder'),
            t.Key('rpc-listen-addr'): tx.HostPortPair(allow_blank_host=True),
            t.Key('user-uid'): t.Int,
            t.Key('user-gid'): t.Int
        }),
        t.Key('storage'): t.Dict({
            t.Key('mode'): t.Enum('xfs', 'btrfs'),
            t.Key('path'): t.String
        })
    }).allow_extra('*')

    # Determine where to read configuration.
    raw_cfg, cfg_src_path = config.read_from_file(config_path, 'agent')

    config.override_with_env(raw_cfg, ('etcd', 'namespace'), 'BACKEND_NAMESPACE')
    config.override_with_env(raw_cfg, ('etcd', 'addr'), 'BACKEND_ETCD_ADDR')
    config.override_with_env(raw_cfg, ('etcd', 'user'), 'BACKEND_ETCD_USER')
    config.override_with_env(raw_cfg, ('etcd', 'password'), 'BACKEND_ETCD_PASSWORD')
    config.override_with_env(raw_cfg, ('agent', 'rpc-listen-addr', 'host'),
                             'BACKEND_AGENT_HOST_OVERRIDE')
    config.override_with_env(raw_cfg, ('agent', 'rpc-listen-addr', 'port'),
                             'BACKEND_AGENT_PORT')

    if debug:
        config.override_key(raw_cfg, ('debug', 'enabled'), True)
        config.override_key(raw_cfg, ('logging', 'level'), 'DEBUG')
        config.override_key(raw_cfg, ('logging', 'pkg-ns', 'ai.backend'), 'DEBUG')

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
        setproctitle('Backend.AI: Storage Agent')
        logger = Logger(cfg['logging'])
        with logger:
            log.info('Backend.AI Storage Agent', VERSION)

            log_config = logging.getLogger('ai.backend.agent.config')
            if debug:
                log_config.debug('debug mode enabled.')

            if 'debug' in cfg and cfg['debug']['enabled']:
                print('== Agent configuration ==')
                pprint(cfg)

            aiotools.start_server(server_main, num_workers=1,
                                    use_threading=True, args=(cfg, ))
            log.info('exit.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
