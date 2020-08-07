# Backend.AI Storage Proxy
Backend.AI Storage Agent is a RPC daemon to manage vfolders used in Backend.AI agent, with quota and storage-specific optimization support.

## Package Structure
* `ai.backend.aiotusclient`
  - `client`: The client which intialize session creation and fle upload url
  - `uploader`
    - The class which divides the file into chunks and uploads to tus server

## Installation
### Prequisites
* Python 3.6 or higher with [pyenv](https://github.com/pyenv/pyenv)
and [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv) (optional but recommneded)
* Backend.AI client sdk
* asyncio
* aiohttp
* tqdm

### Installation Process

First, prepare the source clone of this agent:
```console
# git clone https://github.com/lablup/aiotusclient
```
Put aiotusclient into Backend.AI client SDK top level directory. Which contains directories Manager, client, Agent.

From now on, let's assume all shell commands are executed inside the virtualenv.

Now install dependencies:
```console
# pip install -U -e .
```

