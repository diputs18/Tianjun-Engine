from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tianjun.application.control_plane import CentralControlPlane
from tianjun.domain import Node, ResourceVector, Task, TaskStatus
from tianjun.interfaces.http.server import build_http_server


BRIDGE = Path("examples/cloudsimplus/src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java")
PROBE = Path("tests/cloudsim/TianjunBridgeIntegrationProbe.java")


@pytest.mark.skipif(
    shutil.which("javac") is None or shutil.which("java") is None,
    reason="JDK is required for the CloudSim Java bridge integration test",
)
def test_java_cloudsim_bridge_acknowledges_lease_and_reports_result(tmp_path) -> None:
    classes = tmp_path / "classes"
    classes.mkdir()
    subprocess.run(
        ["javac", "-encoding", "UTF-8", "-d", str(classes), str(BRIDGE), str(PROBE)],
        check=True,
        capture_output=True,
        text=True,
    )

    control = CentralControlPlane()
    control.register_node(Node(
        node_id="java-node",
        region="dc1",
        capacity=ResourceVector(cpu=4, memory=8, storage=20),
    ))
    control.submit_task(Task(
        task_id="java-task",
        task_type="batch",
        demand=ResourceVector(cpu=1, memory=1, storage=1),
        estimated_duration=2,
    ))
    server = build_http_server(control, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        completed = subprocess.run(
            [
                "java",
                "-cp",
                str(classes),
                "org.cloudsimplus.examples.tianjun.TianjunBridgeIntegrationProbe",
                base_url,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert "TIANJUN_CLOUDSIM_BRIDGE_OK java-task" in completed.stdout
    assert control.tasks["java-task"].status == TaskStatus.SUCCEEDED
    assert len(control.execution_history) == 1
    assert control.execution_history[0].stdout_excerpt == "java bridge completed"
