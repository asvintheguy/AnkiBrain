import asyncio
import atexit
import json
import platform
import subprocess

from InterprocessCommand import InterprocessCommand


class ExternalScriptManager:
    def __init__(self, python_path, script_path):
        self.python_path = python_path
        self.script_path = script_path
        self.process = None
        self.lock = asyncio.Lock()

    async def start(self):
        creationflags = 0
        if platform.system() == 'Windows':
            creationflags = subprocess.CREATE_NO_WINDOW

        self.process = await asyncio.create_subprocess_exec(
            self.python_path,
            self.script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,  # Inherit stderr; an unread pipe can deadlock dependency startup.
            creationflags=creationflags,
            limit=16 * 1024 * 1024
        )

        atexit.register(self.terminate_sync)

        # Wait for the ready message from external script.
        print('Waiting for ChatAI Ready Message')
        ready_msg = await self.process.stdout.readline()

        if not ready_msg:
            raise RuntimeError('ChatAI exited before startup. Check the local Python environment and dependencies.')
        ready_data = json.loads(ready_msg.decode().strip())
        if ready_data.get('status') != 'success':
            raise RuntimeError(ready_data.get('data', {}).get('error', 'Error starting ChatAI module'))
        print('Completed startup of ChatAI module')

    async def stop(self):
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()

    def terminate_sync(self):
        if self.process is None or self.process.returncode is not None:
            return

        print('Terminating ChatAI subprocess...')
        self.process.terminate()

    async def call(self, input_data: dict[str, str]) -> dict[str, str]:
        # Serialize the whole request/response pair, not just writes. CLI calls can be slow.
        async with self.lock:
            self.process.stdin.write(json.dumps(input_data).encode() + b'\n')
            await self.process.stdin.drain()
            output_str = await self.process.stdout.readline()
            if not output_str:
                raise RuntimeError('ChatAI stopped before returning a response. Restart AI and try again.')
            output_data = json.loads(output_str.decode().strip())

        if output_data['cmd'] == InterprocessCommand.SUBMODULE_ERROR.value:
            raise RuntimeError(output_data['data']['error'])
        return output_data
