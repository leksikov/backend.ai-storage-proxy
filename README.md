# Backend.AI storage proxy
aiotusclient custom implementation of py-tus-client for backend.ai

## Package Structure
* `ai.backend.storage`
  - `server`: The agent daemon which communicates between Backend.AI Manager
  - `vfs`
    - The minimal fallback backend which only uses the standard Linux filesystem interfaces
  - `xfs`
    - XFS-optimized backend with a small daemon to manage XFS project IDs for quota limits
    - `agent`: Implementation of `AbstractVolumeAgent` with XFS support
  - `purestorage`
    - PureStorage-optimized backend with RapidFile Toolkit (formerly PureTools)
  - `cephfs`
    - CephFS-optimized backend with quota limit support

## Installation
### Prequisites
* Native support for XFS filesystem
* Python 3.6 or higher with [pyenv](https://github.com/pyenv/pyenv)
and [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) (optional but recommneded)
* Access to root shell

### Installation Process

First, prepare the source clone of this agent:
```console
# git clone https://github.com/lablup/backend.ai-storage-agent
```

From now on, let's assume all shell commands are executed inside the virtualenv.

Now install dependencies:
```console
# pip install -U -r requirements.txt
```

Then, copy halfstack.toml to root of the project folder and edit to match your machine:
```console
# cp config/halfstack.toml agent.toml
```

When done, start storage server with root privilege:
```console
# python -m ai.backend.storage.server
```

This command will start Storage Agent daemon binded to `127.0.0.1:6020`.

Now start Backent.AI Agent with `scratch-type` to `volume-agent`.

#### For testing: Create virtual XFS device
It'll be better to create a virtual block device mounted to `lo` if you're only using this storage agent for testing. To achieve that:
1. Create file with your desired size
```console
# dd if=/dev/zero of=xfs_test.img bs=1G count=100
```
2. Make file as XFS partition
```console
# mkfs.xfs xfs_test.img
```
3. Mount it to loopback
```console
# export LODEVICE=$(losetup -f)
# losetup $LODEVICE xfs_test.img
```
4. Create mount point and mount loopback device, with pquota option
```console
# mkdir -p /xfs
# mount -o loop -o pquota $LODEVICE /xfs
