import logging
from pathlib import Path
import shutil
import os

from ai.backend.common.logging import BraceStyleAdapter

from ..server import AbstractVolumeAgent, run

log = BraceStyleAdapter(logging.getLogger('ai.backend.storage.server'))

class VolumeAgent(AbstractVolumeAgent):
    def __init__(self, mount_path, uid, gid):
        self.registry = {}
        self.project_id_pool = []
        self.mount_path = mount_path
        self.uid = uid
        self.gid = gid

    async def init(self):
        log.setLevel(logging.DEBUG)
        with open('/etc/projid', 'r') as fr:
            for line in fr.readlines():
                proj_name, proj_id = line.split(':')[:2]
                self.project_id_pool.append(int(proj_id))

    async def create(self, kernel_id: str, size: str) -> str:
        project_id = -1

        if kernel_id in self.registry.keys():
            return

        for i in range(len(self.project_id_pool)-1):
            if self.project_id_pool[i] + 1 != self.project_id_pool[i + 1]:
                project_id = self.project_id_pool[i] + 1
                break
        if len(self.project_id_pool) == 0:
            project_id = 1
        if project_id == -1:
            project_id = self.project_id_pool[-1] + 1

        folder_path = (Path(self.mount_path) / kernel_id).resolve()

        os.mkdir(folder_path)
        os.chown(folder_path, self.uid, self.gid)

        with open('/etc/projects', 'w+') as fw:
            fw.write(f'{project_id}:{folder_path}')
        with open('/etc/projid', 'w+') as fw:
            fw.write(f'{kernel_id}:{project_id}')

        out, err = await run(f'xfs_quota -x -c "project -s {kernel_id}" {self.mount_path}')
        out, err = await run(f'xfs_quota -x -c "limit -p bhard={size} {kernel_id}" {self.mount_path}')
        self.registry[kernel_id] = project_id
        self.project_id_pool += [project_id]
        self.project_id_pool.sort()

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

        shutil.rmtree(Path(self.mount_path) / kernel_id)
        self.project_id_pool.remove(self.registry[kernel_id])
        del self.registry[kernel_id]

    async def get(self, kernel_id: str) -> str:
        return (Path(self.mount_path) / kernel_id).resolve()
