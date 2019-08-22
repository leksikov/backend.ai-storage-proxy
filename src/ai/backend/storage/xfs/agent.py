import logging
from pathlib import Path
import os

from ai.backend.common.logging import BraceStyleAdapter

from ..server import AbstractVolumeAgent, run

log = BraceStyleAdapter(logging.getLogger('ai.backend.storage.xfs.agent'))


class VolumeAgent(AbstractVolumeAgent):
    def __init__(self, mount_path):
        self.registry = {}
        self.project_id_pool = []
        self.mount_path = mount_path

    async def init(self):
        pass

    async def create(self, kernel_id: str, size: str) -> str:
        project_id = -1

        if kernel_id in self.registry.keys():
            return

        for i in range(len(self.project_id_pool)):
            if self.project_id_pool[i] + 1 != self.project_id_pool[i + 1]:
                project_id = self.project_id_pool[i] + 1
                break

        if project_id == -1:
            project_id = self.project_id_pool[-1] + 1

        folder_path = (Path(self.mount_path) / kernel_id).resolve()

        os.mkdir(folder_path)

        with open('/etc/projects', 'w+') as fw:
            fw.write(f'{project_id}:{folder_path}')
        with open('/etc/projid', 'w+') as fw:
            fw.write(f'{kernel_id}:{project_id}')

        out, err = await run(f'xfs_quota -x -c "project -s {kernel_id}" {self.mount_path}')
        out, err = await run(f'xfs_quota -x -c "limit -p bhard={size} {kernel_id}" {self.mount_path}')
        self.registry[kernel_id] = project_id
        self.project_id_pool = (self.project_ids + [kernel_id]).sort()

        return folder_path

    async def remove(self, kernel_id: str):
        if kernel_id not in self.registry.keys():
            return

        out, err = await run(f'xfs_quota -x -c "limit -p bsoft=0 bhard=0 {kernel_id}" {self.mount_path}')

        new_projects = ''
        new_projid = ''

        with open('/etc/projects', 'r') as fr:
            for line in fr.readlines():
                if line.startswith(str(self.registry[kernel_id]) + ':'):
                    continue
                new_projects += (line + '\n')
        with open('/etc/projid', 'r') as fr:
            for line in fr.readlines():
                if line.startswith(kernel_id + ':'):
                    continue
                new_projid += (line + '\n')

        with open('/etc/projects', 'w') as fw:
            fw.write(new_projects)
        with open('/etc/projid', 'w') as fw:
            fw.write(new_projid)

        self.project_id_pool.remove(self.registry[kernel_id])
        del self.registry[kernel_id]

    async def get(self, kernel_id: str) -> str:
        return (Path(self.mount_path) / kernel_id).resolve()
