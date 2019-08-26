# Backend.AI Storage Agent
Backend.AI Storage Agent is a RPC daemon to manage directories used in Backend.AI agent, with quotation limit support.   

## Package Structure
* `ai.backend.storage`
    - `server`: The agent daemon which communicates between Backend.AI agent
    - `xfs`: 
        - `agent`: Implementation of `AbstractVolumeAgent` with XFS support

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

Then, copy the sample.toml and edit the TOML to match your system:
```console
# cp config/sample.toml agent.toml
```

When done, start storage server with root privilege:
```console
# python -m ai.backend.storage.server
```

This command will start Storage Agent daemon binded to `127.0.0.1:6020`.

Now start Backent.AI Agent with `scratch-type` to `volume-agent`.
