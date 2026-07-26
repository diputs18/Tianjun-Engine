package org.cloudsimplus.examples.tianjun;

import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.LeaseResult;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.SimTaskResult;

public final class TianjunBridgeIntegrationProbe {
    private TianjunBridgeIntegrationProbe() {
    }

    public static void main(final String[] args) {
        final TianjunHttpBridge bridge = new TianjunHttpBridge(args[0]);
        if (!bridge.isHealthy()) {
            throw new IllegalStateException("Python control plane is not healthy");
        }
        final LeaseResult lease = bridge.requestLease("java-node");
        if (lease == null || lease.taskId().isBlank()) {
            throw new IllegalStateException("Java bridge did not receive a lease");
        }
        bridge.reportResult(new SimTaskResult(
            "java-node",
            lease.taskId(),
            true,
            1.0,
            "java bridge completed",
            "",
            0,
            1.0
        ));
        System.out.println("TIANJUN_CLOUDSIM_BRIDGE_OK " + lease.taskId());
    }
}
