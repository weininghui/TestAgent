"""Docker test environment — compile and run GTest inside a container.

Usage::

    from agents.container_env import ContainerEnv

    env = ContainerEnv()
    if env.is_available():
        result = env.compile_and_run("./output/generated", "MySDK")
        print(result["output"])
        env.cleanup()

The container uses ``ubuntu:22.04`` with ``build-essential``, ``cmake``,
and ``libgtest-dev`` pre-installed.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONTAINER_IMAGE = "sdk-test-env:latest"
_DOCKERFILE_CONTENT = """FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential cmake libgtest-dev git ca-certificates \\
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
"""


class ContainerEnv:
    """Manage a Docker container for GTest compilation and execution.

    The container is ephemeral — created on demand and removed after use.
    Project source and generated test code are bind-mounted into the
    container's ``/workspace`` directory.
    """

    def __init__(self, image: str = _CONTAINER_IMAGE) -> None:
        self.image = image
        self.container_id: str | None = None
        self._image_built = False

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Check whether Docker is installed and responsive."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ------------------------------------------------------------------
    # Image management
    # ------------------------------------------------------------------

    def build_image(self, force: bool = False) -> bool:
        """Build the test environment Docker image.

        Returns ``True`` if the image was built (or was already present).
        """
        if not force and self._image_built:
            return True

        # Check if image already exists
        check = subprocess.run(
            ["docker", "image", "inspect", self.image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if check.returncode == 0 and not force:
            self._image_built = True
            logger.info("Docker image %s already exists", self.image)
            return True

        logger.info("Building Docker image %s ...", self.image)
        try:
            # Build via stdin pipe (no temp file needed)
            proc = subprocess.run(
                ["docker", "build", "--tag", self.image, "--file", "-", "."],
                input=_DOCKERFILE_CONTENT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                logger.error("Docker build failed:\n%s", proc.stderr)
                return False
            self._image_built = True
            logger.info("Docker image %s built successfully", self.image)
            return True
        except subprocess.TimeoutExpired:
            logger.error("Docker build timed out (120s)")
            return False

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def create(
        self,
        mount_dir: str,
        container_name: str | None = None,
    ) -> str | None:
        """Create and start a test container with *mount_dir* bind-mounted.

        Returns the container ID on success, ``None`` on failure.
        """
        if not self.build_image():
            return None

        abs_mount = str(Path(mount_dir).resolve())
        name_args = ["--name", container_name] if container_name else []

        try:
            result = subprocess.run(
                [
                    "docker", "run", "--detach",
                    "--rm",
                    *name_args,
                    "--mount", f"type=bind,source={abs_mount},target=/workspace",
                    self.image,
                    "tail", "-f", "/dev/null",  # keep container alive
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.error("Container create failed:\n%s", result.stderr)
                return None
            self.container_id = result.stdout.strip()
            logger.info("Container %s created (mount: %s)", self.container_id[:12], abs_mount)
            return self.container_id
        except subprocess.TimeoutExpired:
            logger.error("Container create timed out")
            return None

    def exec(self, cmd: list[str], timeout: int = 120) -> dict[str, Any]:
        """Run a command inside the container.

        Returns ``{"returncode": int, "output": str, "error": str}``.
        """
        if not self.container_id:
            return {"returncode": -1, "output": "", "error": "No container running"}

        try:
            result = subprocess.run(
                ["docker", "exec", self.container_id] + cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "returncode": result.returncode,
                "output": result.stdout,
                "error": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {"returncode": -1, "output": "", "error": f"Timed out ({timeout}s)"}

    def stop(self) -> None:
        """Stop and remove the container."""
        if self.container_id:
            try:
                subprocess.run(
                    ["docker", "stop", self.container_id],
                    capture_output=True,
                    timeout=30,
                )
                logger.info("Container %s stopped", self.container_id[:12])
            except Exception as exc:
                logger.warning("Failed to stop container: %s", exc)
            self.container_id = None

    def cleanup(self) -> None:
        """Alias for :meth:`stop`."""
        self.stop()

    def __enter__(self) -> "ContainerEnv":
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Test compilation & execution
    # ------------------------------------------------------------------

    def compile_and_run(
        self,
        gen_dir: str,
        sdk_name: str | None = None,
        container_name: str | None = None,
    ) -> dict[str, Any]:
        """Compile and run GTest in a container from generated sources.

        Steps
        -----
        1. Create container (if not already running) with *gen_dir* mounted.
        2. Run ``cmake -B build && cmake --build build``.
        3. Run ``ctest --output-on-failure`` (or the test binary directly).

        Parameters
        ----------
        gen_dir:
            Directory containing the generated CMakeLists.txt + ``.cpp`` files.
        sdk_name:
            Optional SDK/project name (used as binary name).  Defaults to
            auto-detection from the first ``.cpp`` file in *gen_dir*.

        Returns
        -------
        dict
            Keys: ``success`` (bool), ``build_output`` (str), ``test_output``
            (str), ``error`` (str).
        """
        if not self.container_id:
            cid = self.create(mount_dir=gen_dir, container_name=container_name)
            if not cid:
                return {
                    "success": False,
                    "build_output": "",
                    "test_output": "",
                    "error": "Failed to create container",
                }

        # --- Step 1: CMake configure ---
        logger.info("Container: cmake configure ...")
        cfg = self.exec(["cmake", "-B", "build", "-S", "/workspace"], timeout=60)

        if cfg["returncode"] != 0:
            return {
                "success": False,
                "build_output": cfg["output"] + "\n" + cfg["error"],
                "test_output": "",
                "error": "CMake configuration failed",
            }

        # --- Step 2: Build ---
        logger.info("Container: cmake build ...")
        build = self.exec(
            ["cmake", "--build", "build", "--verbose"],
            timeout=180,
        )

        if build["returncode"] != 0:
            return {
                "success": False,
                "build_output": build["output"] + "\n" + build["error"],
                "test_output": "",
                "error": "Build failed (compilation error)",
            }

        # --- Step 3: Run tests ---
        logger.info("Container: ctest ...")
        test = self.exec(
            ["ctest", "--test-dir", "build", "--output-on-failure"],
            timeout=300,
        )

        return {
            "success": test["returncode"] == 0,
            "build_output": cfg["output"] + "\n" + build["output"],
            "test_output": test["output"] + "\n" + test["error"],
            "error": "" if test["returncode"] == 0 else test["output"] + test["error"],
        }
