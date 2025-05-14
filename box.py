import asyncio
import os
import uvicorn
from fastapi import FastAPI

from syft_core import Client as SyftboxClient
from syft_core import SyftClientConfig
from syft_event import SyftEvents
from resources import ensure_syft_yaml, add_dataset, load_schema

class SyftboxApp:
    def __init__(self, app_name: str, app: FastAPI, client: SyftboxClient = None):
        self.app_name = app_name
        self.app = app

        # Use the provided client or create a new one
        self.client = client if client is not None else SyftboxClient(SyftClientConfig.load())
        self.config = self.client.config
        self.box = SyftEvents(app_name)

        # Setup datasite path
        self.wrapped_path = self.client.datasite_path / "public" / app_name
        self.client.makedirs(self.wrapped_path)

        ensure_syft_yaml(self.client)

    def get_assigned_port(self):
        return int(os.getenv("SYFTBOX_ASSIGNED_PORT", 8080))

    async def _run(self, host: str, port: int, reload: bool):
        task_box = asyncio.create_task(asyncio.to_thread(self.box.run_forever))
        config = uvicorn.Config(app=self.app, host=host, port=port, reload=reload)
        server = uvicorn.Server(config)

        await asyncio.gather(task_box, server.serve())

    def run(self, host: str = "0.0.0.0", port: int | str = None, reload: bool = True):
        if port is None or port == 'auto':
            port = self.get_assigned_port()
        print(f"Running server on host: {host}, port: {port}, with reload set to: {reload}")
        asyncio.run(self._run(host, port, reload))
