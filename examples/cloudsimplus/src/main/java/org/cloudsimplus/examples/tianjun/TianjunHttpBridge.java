package org.cloudsimplus.examples.tianjun;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Minimal HTTP bridge between CloudSim Plus and the Python Tianjun control plane.
 */
public class TianjunHttpBridge {
    private static final Pattern NODE_ID_PATTERN = Pattern.compile("\"node_id\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern TASK_ID_PATTERN = Pattern.compile("\"task_id\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern STATUS_PATTERN = Pattern.compile("\"status\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern SCORE_PATTERN = Pattern.compile("\"total_score\"\\s*:\\s*([0-9.]+)");
    private static final Pattern LEASE_TASK_PATTERN = Pattern.compile("\"lease\"\\s*:\\s*\\{\\s*\"task_id\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern ESTIMATED_DURATION_PATTERN = Pattern.compile("\"estimated_duration\"\\s*:\\s*([0-9]+)");
    private static final Pattern PREDICTED_COST_PATTERN = Pattern.compile("\"predicted_cost\"\\s*:\\s*([0-9.]+)");
    private static final Pattern BATCH_ID_PATTERN = Pattern.compile("\"batch_id\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern PLAN_ID_PATTERN = Pattern.compile("\"plan_id\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern SNAPSHOT_VERSION_PATTERN = Pattern.compile("\"resource_snapshot_version\"\\s*:\\s*([0-9]+)");

    private final HttpClient client;
    private final String server;
    private final Map<String, Double> lastHeartbeatTickByNode = new ConcurrentHashMap<>();

    public TianjunHttpBridge(final String server) {
        this.server = stripTrailingSlash(server);
        this.client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    }

    public boolean isHealthy() {
        try {
            final String body = get("/health");
            return body.contains("\"ok\"");
        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        }
    }

    public void registerNode(final SimNode node) {
        post("/nodes/register", nodeRegistrationJson(node));
    }

    public void registerTopology(final String topologyJson) {
        post("/topology/register", topologyJson);
    }

    public void registerNode(final SimNode node, final Map<String, NetworkPath> networkPaths) {
        post("/nodes/register", nodeRegistrationJson(node, networkPathsJson(networkPaths)));
    }

    public void heartbeat(final SimNode node, final double tick) {
        heartbeat(node, tick, 0.0, 0.0, 0.0);
    }

    public void heartbeat(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double ramUtilization,
        final double bandwidthUtilization
    ) {
        post("/nodes/heartbeat", heartbeatJson(node, tick, cpuUtilization, ramUtilization, bandwidthUtilization));
    }

    public void heartbeat(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double ramUtilization,
        final double bandwidthUtilization,
        final Map<String, NetworkPath> networkPaths
    ) {
        post("/nodes/heartbeat", heartbeatJson(
            node,
            tick,
            cpuUtilization,
            ramUtilization,
            bandwidthUtilization,
            networkPathsJson(networkPaths)
        ));
    }

    public boolean tryHeartbeat(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double ramUtilization,
        final double bandwidthUtilization
    ) {
        try {
            heartbeat(node, tick, cpuUtilization, ramUtilization, bandwidthUtilization);
            return true;
        } catch (IllegalStateException e) {
            return false;
        }
    }

    public boolean tryHeartbeat(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double ramUtilization,
        final double bandwidthUtilization,
        final Map<String, NetworkPath> networkPaths
    ) {
        try {
            heartbeat(node, tick, cpuUtilization, ramUtilization, bandwidthUtilization, networkPaths);
            return true;
        } catch (IllegalStateException e) {
            return false;
        }
    }

    public SchedulingResult previewSchedule(final SimTask task) {
        final String response = post("/schedule/preview", taskJson(task));
        final String status = matchString(STATUS_PATTERN, response, "unknown");
        final String nodeId = matchString(NODE_ID_PATTERN, response, "");
        final double score = matchDouble(SCORE_PATTERN, response, 0.0);
        return new SchedulingResult(status, nodeId, task.taskId(), score, response);
    }

    public SchedulingResult commitSchedule(final SimTask task) {
        final String response = post("/schedule/commit", taskJson(task));
        final String status = matchString(STATUS_PATTERN, response, "unknown");
        final String nodeId = matchString(NODE_ID_PATTERN, response, "");
        final String leaseTaskId = matchString(LEASE_TASK_PATTERN, response, task.taskId());
        final double score = matchDouble(SCORE_PATTERN, response, 0.0);
        return new SchedulingResult(status, nodeId, leaseTaskId, score, response);
    }

    public String getBatchActualMetrics(final String batchId) {
        try {
            return get("/task-batches/" + batchId + "/metrics");
        } catch (IOException | InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Unable to read Tianjun batch metrics", e);
        }
    }

    public void submitTask(final SimTask task) {
        post("/tasks", taskJson(task));
    }

    /** Imports, jointly previews and atomically commits one CloudSim batch. */
    public BatchPlanResult commitTaskBatch(
        final String clientBatchId,
        final String batchName,
        final List<SimTask> tasks,
        final String strategy
    ) {
        final String imported = post("/task-batches/import", batchJson(clientBatchId, batchName, tasks));
        final String batchId = matchString(BATCH_ID_PATTERN, imported, "");
        if (batchId.isBlank()) {
            throw new IllegalStateException("Batch import did not return batch_id: " + imported);
        }
        final boolean calibratedGreen = "B6-green-calibrated-v1".equalsIgnoreCase(strategy);
        final boolean greenSingleObjective = "B6-green-single-v1".equalsIgnoreCase(strategy);
        final boolean greenSlaDualObjective = "B6-green-sla-dual-v1".equalsIgnoreCase(strategy);
        final boolean greenSla85DualObjective = "B6-green-sla-85-v1".equalsIgnoreCase(strategy);
        final boolean greenSla90DualObjective = "B6-green-sla-90-v1".equalsIgnoreCase(strategy);
        final String schedulerStrategy = calibratedGreen || greenSingleObjective || greenSlaDualObjective || greenSla85DualObjective || greenSla90DualObjective
            ? "B6-hierarchical-batch"
            : strategy;
        final String groupWeights = calibratedGreen
            ? ", \"group_weights\": {\"sla_quality\": 0.18, \"network_coordination\": 0.05, "
                + "\"resource_efficiency\": 0.15, \"economic_cost\": 0.02, \"green_carbon\": 0.60}"
            : greenSingleObjective
                ? ", \"active_groups\": [\"green_carbon\"], \"group_weights\": {\"green_carbon\": 1.0}"
                : greenSlaDualObjective
                    ? ", \"active_groups\": [\"green_carbon\", \"sla_quality\"], "
                        + "\"group_weights\": {\"green_carbon\": 0.70, \"sla_quality\": 0.30}"
                    : greenSla85DualObjective
                        ? ", \"active_groups\": [\"green_carbon\", \"sla_quality\"], "
                            + "\"group_weights\": {\"green_carbon\": 0.85, \"sla_quality\": 0.15}"
                        : greenSla90DualObjective
                            ? ", \"active_groups\": [\"green_carbon\", \"sla_quality\"], "
                                + "\"group_weights\": {\"green_carbon\": 0.90, \"sla_quality\": 0.10}"
                            : "";
        final String preview = post("/task-batches/" + batchId + "/preview", """
            {"strategy": "%s", "simulation_tick": 0%s}
            """.formatted(escapeJson(schedulerStrategy), groupWeights));
        final String planId = matchString(PLAN_ID_PATTERN, preview, "");
        final int snapshotVersion = matchInt(SNAPSHOT_VERSION_PATTERN, preview, -1);
        if (planId.isBlank() || snapshotVersion < 0) {
            throw new IllegalStateException("Batch preview did not return a committable plan: " + preview);
        }
        final String committed = post("/task-batches/" + batchId + "/commit", """
            {"plan_id": "%s", "resource_snapshot_version": %d, "confirmed_by_user_button": true}
            """.formatted(escapeJson(planId), snapshotVersion));
        return new BatchPlanResult(batchId, planId, snapshotVersion, strategy, committed);
    }

    public LeaseResult requestLease(final String nodeId) {
        final String response = post("/leases/next", """
            {"node_id": "%s"}
            """.formatted(escapeJson(nodeId)));
        if (response == null || response.isBlank() || "null".equals(response.trim())) {
            return null;
        }
        final String taskId = matchString(TASK_ID_PATTERN, response, "");
        if (taskId.isBlank()) {
            return null;
        }
        return new LeaseResult(
            taskId,
            matchString(NODE_ID_PATTERN, response, nodeId),
            response,
            matchInt(ESTIMATED_DURATION_PATTERN, response, 2),
            matchDouble(PREDICTED_COST_PATTERN, response, 4.0)
        );
    }

    public void reportProgress(final SimTaskProgress progress) {
        post("/task-runs/progress", progressJson(progress));
    }

    public void reportResult(final SimTaskResult result) {
        post("/task-runs/result", resultJson(result));
    }

    private String get(final String path) throws IOException, InterruptedException {
        final HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(server + path))
            .timeout(Duration.ofSeconds(15))
            .GET()
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)).body();
    }

    private String post(final String path, final String json) {
        final HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(server + path))
            .timeout(Duration.ofSeconds(20))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(json, StandardCharsets.UTF_8))
            .build();
        try {
            final HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() >= 400) {
                throw new IllegalStateException("Tianjun API " + path + " failed: " + response.body());
            }
            return response.body();
        } catch (IOException e) {
            throw new IllegalStateException("Cannot reach Tianjun API " + server + path, e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while calling Tianjun API " + server + path, e);
        }
    }

    private String nodeRegistrationJson(final SimNode node) {
        return nodeRegistrationJson(node, networkPathsJson(node, 0.0, 0.0, 0.0));
    }

    private String nodeRegistrationJson(final SimNode node, final String networkPaths) {
        return """
            {
              "node_id": "%s",
              "region": "%s",
              "location": "%s",
              "service_region": "%s",
              "site_id": "%s",
              "labels": ["cloudsim", "cpu", "gpu", "%s", "latency-sensitive"],
              "capacity": {"cpu": %.4f, "memory": %.4f, "gpu": %.4f, "storage": %.4f, "mips": %.4f, "gpu_memory": %.4f, "storage_iops": %.4f, "bandwidth": %.4f},
              "cost_per_tick": %.4f,
              "base_reliability": %.4f,
              "power_profile": {"profile_id": "%s", "idle_power_w": %.4f, "max_power_w": %.4f, "gpu_idle_power_w": %.4f, "gpu_max_power_w": %.4f},
              "carbon_profile": {"site_id": "%s", "region": "%s", "pue": %.4f, "carbon_intensity_g_per_kwh": %.4f, "carbon_intensity_trace": %s, "carbon_signal_type": "synthetic_average", "timezone": "Asia/Shanghai", "source_version": "cloudsim-v1"},
              "performance_factors": {"inference": %.4f, "batch_cpu": %.4f, "analytics": %.4f, "streaming": %.4f},
              "network_paths": %s
            }
            """.formatted(
            node.nodeId(),
            node.region(),
            node.location(),
            node.serviceRegion(),
            node.siteId(),
            node.region(),
            node.cpu(),
            node.memoryGb(),
            node.gpu(),
            node.storageGb(),
            node.totalMips(),
            node.gpuMemoryGb(),
            node.storageIops(),
            node.bandwidthMbps(),
            node.costPerTick(),
            node.reliability(),
            node.powerProfileId(),
            node.idlePowerW(),
            node.maxPowerW(),
            node.gpuIdlePowerW(),
            node.gpuMaxPowerW(),
            node.siteId(),
            node.region(),
            node.pue(),
            node.carbonIntensityAt(0.0),
            carbonIntensityTraceJson(node),
            node.performanceFactor(),
            node.performanceFactor(),
            node.performanceFactor(),
            node.performanceFactor(),
            networkPaths
        );
    }

    private String heartbeatJson(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double ramUtilization,
        final double bandwidthUtilization
    ) {
        return heartbeatJson(
            node,
            tick,
            cpuUtilization,
            ramUtilization,
            bandwidthUtilization,
            networkPathsJson(node, tick, cpuUtilization, bandwidthUtilization)
        );
    }

    private String heartbeatJson(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double ramUtilization,
        final double bandwidthUtilization,
        final String networkPaths
    ) {
        final double loadWave = 0.5 + (Math.sin((tick + node.index()) * 0.35) * 0.5);
        final double loadPressure = clamp(cpuUtilization * 0.55 + ramUtilization * 0.25 + bandwidthUtilization * 0.20, 0.0, 1.0);
        final double health = clamp(0.96 - loadWave * 0.08 - loadPressure * 0.22 - node.risk() * 0.08, 0.45, 0.99);
        final double reliability = clamp(node.reliability() - node.risk() * 0.035 - loadPressure * 0.025, 0.45, 0.999);
        final double powerW = node.idlePowerW() + (node.maxPowerW() - node.idlePowerW()) * loadPressure;
        final double carbonIntensity = node.carbonIntensityAt(tick);
        final Double previousTick = lastHeartbeatTickByNode.put(node.nodeId(), tick);
        final double intervalSeconds = previousTick == null ? 0.0 : Math.max(0.0, tick - previousTick);
        final double energyKwhDelta = powerW * intervalSeconds / 3_600_000.0;
        return """
            {
              "node_id": "%s",
              "health_score": %.4f,
              "online": true,
              "cost_per_tick": %.4f,
              "region": "%s",
              "location": "%s",
              "service_region": "%s",
              "labels": ["cloudsim", "cpu", "gpu", "%s", "latency-sensitive"],
              "performance_factors": {"inference": %.4f, "batch_cpu": %.4f, "analytics": %.4f, "streaming": %.4f},
              "network_paths": %s,
              "sim_tick": %.4f,
              "simulated": true,
              "telemetry": {"cpu_utilization": %.6f, "ram_utilization": %.6f, "bandwidth_utilization": %.6f, "heartbeat_interval_seconds": %.6f},
              "reliability_score": %.4f,
              "power_w": %.4f,
              "energy_kwh_delta": %.8f,
              "carbon_intensity_g_per_kwh": %.4f,
              "carbon_signal_timestamp": %.4f
            }
            """.formatted(
            node.nodeId(),
            health,
            node.costPerTick(),
            node.region(),
            node.location(),
            node.serviceRegion(),
            node.region(),
            node.performanceFactor(),
            node.performanceFactor(),
            node.performanceFactor(),
            node.performanceFactor(),
            networkPaths,
            tick,
            clamp(cpuUtilization, 0.0, 1.0),
            clamp(ramUtilization, 0.0, 1.0),
            clamp(bandwidthUtilization, 0.0, 1.0),
            intervalSeconds,
            reliability,
            powerW,
            energyKwhDelta,
            carbonIntensity,
            tick
        );
    }

    private String taskJson(final SimTask task) {
        return """
            {
              "task_id": "%s",
              "task_type": "%s",
              "demand": {"cpu": %.4f, "memory": %.4f, "gpu": %.4f, "storage": %.4f, "mips": %.4f, "gpu_memory": %.4f, "storage_iops": %.4f, "bandwidth": %.4f},
              "estimated_duration": %d,
              "priority": %d,
              "budget": %.4f,
              "deadline": %d,
              "data_region": "%s",
              "source_region": "%s",
              "input_size_gb": %.4f,
              "max_latency_ms": %.4f,
              "min_bandwidth_mbps": %.4f,
              "network_sensitivity": %.4f,
              "carbon_budget_g": %.6f,
              "carbon_priority": %.4f,
              "expected_cpu_utilization": %.6f,
              "allow_region_shift": %s,
              "allow_time_shift": %s,
              "deferrable_until_tick": %d,
              "batch_id": "%s",
              "preferred_labels": ["cloudsim"]
            }
            """.formatted(
            task.taskId(),
            task.taskType(),
            task.cpu(),
            task.memoryGb(),
            task.gpu(),
            task.storageGb(),
            task.requiredMips(),
            task.gpuMemoryGb(),
            task.storageIops(),
            task.minBandwidthMbps(),
            task.estimatedDuration(),
            task.priority(),
            task.budget(),
            task.deadline(),
            task.sourceRegion(),
            task.sourceRegion(),
            task.inputSizeGb(),
            task.maxLatencyMs(),
            task.minBandwidthMbps(),
            task.networkSensitivity(),
            task.carbonBudgetG(),
            task.carbonPriority(),
            task.expectedCpuUtilization(),
            task.allowRegionShift() ? "true" : "false",
            task.allowTimeShift() ? "true" : "false",
            task.deferrableUntilTick(),
            escapeJson(task.batchId())
        );
    }

    private String resultJson(final SimTaskResult result) {
        return """
            {
              "node_id": "%s",
              "task_id": "%s",
              "success": %s,
              "duration_seconds": %.4f,
              "stdout": "%s",
              "stderr": "%s",
              "returncode": %d,
              "cost": %.4f,
              "energy_kwh": %.8f,
              "compute_carbon_g": %.6f,
              "network_carbon_g": %.6f,
              "operational_carbon_g": %.6f,
              "carbon_scope": "operational_only",
              "metadata": {
                "queue_wait_seconds": %.6f,
                "jct_seconds": %.6f,
                "cpu_utilization": %.6f,
                "memory_utilization": %.6f,
                "bandwidth_utilization": %.6f,
                "storage_utilization": %.6f
              }
            }
            """.formatted(
            result.nodeId(),
            result.taskId(),
            result.success() ? "true" : "false",
            result.durationSeconds(),
            escapeJson(result.stdout()),
            escapeJson(result.stderr()),
            result.returnCode(),
            result.cost(),
            result.energyKwh(),
            result.computeCarbonG(),
            result.networkCarbonG(),
            result.computeCarbonG() + result.networkCarbonG(),
            result.queueWaitSeconds(),
            result.jctSeconds(),
            result.cpuUtilization(),
            result.memoryUtilization(),
            result.bandwidthUtilization(),
            result.storageUtilization()
        );
    }

    private String carbonIntensityTraceJson(final SimNode node) {
        final StringBuilder builder = new StringBuilder("{");
        node.carbonIntensityTrace().entrySet().stream()
            .sorted(Map.Entry.comparingByKey())
            .forEach(entry -> {
                if (builder.length() > 1) {
                    builder.append(',');
                }
                builder.append('\"')
                    .append((int) Math.round(entry.getKey()))
                    .append("\":")
                    .append(String.format(Locale.ROOT, "%.4f", entry.getValue()));
            });
        return builder.append('}').toString();
    }

    private String batchJson(final String clientBatchId, final String batchName, final List<SimTask> tasks) {
        final String taskPayloads = tasks.stream().map(this::taskJson).collect(java.util.stream.Collectors.joining(","));
        return """
            {
              "client_batch_id": "%s",
              "batch_name": "%s",
              "batch_preferences": {"optimization_profile": "cloudsim_validation"},
              "tasks": [%s]
            }
            """.formatted(escapeJson(clientBatchId), escapeJson(batchName), taskPayloads);
    }

    private String progressJson(final SimTaskProgress progress) {
        return """
            {
              "node_id": "%s",
              "task_id": "%s",
              "stage": "%s",
              "status": "%s",
              "progress": %.4f,
              "message": "%s",
              "metrics": {
                "sim_tick": %.4f,
                "simulated_utilization": {
                  "cpu": %.6f,
                  "memory": %.6f,
                  "storage": %.6f
                },
                "bandwidth_utilization": %.6f
              }
            }
            """.formatted(
            progress.nodeId(),
            progress.taskId(),
            escapeJson(progress.stage()),
            escapeJson(progress.status()),
            clamp(progress.progress(), 0.0, 1.0),
            escapeJson(progress.message()),
            progress.tick(),
            clamp(progress.cpuUtilization(), 0.0, 1.0),
            clamp(progress.memoryUtilization(), 0.0, 1.0),
            clamp(progress.storageUtilization(), 0.0, 1.0),
            clamp(progress.bandwidthUtilization(), 0.0, 1.0)
        );
    }

    private String networkPathsJson(
        final SimNode node,
        final double tick,
        final double cpuUtilization,
        final double bandwidthUtilization
    ) {
        final StringBuilder builder = new StringBuilder("{");
        final String[] regions = {"shanghai", "beijing", "hangzhou"};
        for (int i = 0; i < regions.length; i++) {
            if (i > 0) {
                builder.append(",");
            }
            final double regionDistance = Math.abs(regionIndex(node.region()) - i);
            final double wave = Math.sin((tick * 0.17) + node.index() * 0.41 + i * 0.77);
            final double burst = Math.max(0.0, Math.sin((tick * 0.071) + node.index() * 0.19 + i));
            final double pressure = clamp(cpuUtilization * 0.45 + bandwidthUtilization * 0.55, 0.0, 1.0);
            final double baseLatency = 7.0 + regionDistance * 18.0 + node.risk() * 18.0;
            final double latency = Math.max(1.0, baseLatency + Math.abs(wave) * (2.8 + node.risk() * 8.0) + pressure * 9.0 + burst * node.risk() * 10.0);
            final double jitter = 1.2 + regionDistance * 3.6 + node.risk() * 9.0 + Math.abs(wave) * 2.4 + pressure * 4.5;
            final double bandwidth = Math.max(80.0, node.bandwidthMbps() - regionDistance * 160.0 - node.risk() * 180.0 - pressure * 140.0 - burst * 60.0);
            final double packetLoss = clamp(0.001 + regionDistance * 0.006 + node.risk() * 0.025 + pressure * 0.012 + burst * node.risk() * 0.018, 0.0, 0.18);
            final double reliability = clamp(node.reliability() - packetLoss * 1.4, 0.45, 0.999);
            builder.append("""
                "%s": {"latency_ms": %.4f, "jitter_ms": %.4f, "bandwidth_mbps": %.4f, "bandwidth_jitter_mbps": %.4f, "packet_loss": %.6f, "path_reliability": %.6f}
                """.formatted(regions[i], latency, jitter, bandwidth, bandwidth * 0.08 + jitter * 3.0, packetLoss, reliability));
        }
        builder.append("}");
        return builder.toString();
    }

    private String networkPathsJson(final Map<String, NetworkPath> networkPaths) {
        final StringBuilder builder = new StringBuilder("{");
        int index = 0;
        for (final var entry : networkPaths.entrySet().stream().sorted(Map.Entry.comparingByKey(Comparator.naturalOrder())).toList()) {
            if (index++ > 0) {
                builder.append(",");
            }
            final var profile = entry.getValue();
            builder.append("""
                "%s": {"latency_ms": %.4f, "jitter_ms": %.4f, "bandwidth_mbps": %.4f, "bandwidth_jitter_mbps": %.4f, "packet_loss": %.6f, "path_reliability": %.6f}
                """.formatted(
                escapeJson(entry.getKey()),
                profile.latencyMs(),
                profile.jitterMs(),
                profile.bandwidthMbps(),
                profile.bandwidthJitterMbps(),
                profile.packetLoss(),
                profile.pathReliability()
            ));
        }
        builder.append("}");
        return builder.toString();
    }

    private static String stripTrailingSlash(final String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    private static String matchString(final Pattern pattern, final String text, final String fallback) {
        final Matcher matcher = pattern.matcher(text);
        return matcher.find() ? matcher.group(1) : fallback;
    }

    private static double matchDouble(final Pattern pattern, final String text, final double fallback) {
        final Matcher matcher = pattern.matcher(text);
        return matcher.find() ? Double.parseDouble(matcher.group(1)) : fallback;
    }

    private static int matchInt(final Pattern pattern, final String text, final int fallback) {
        final Matcher matcher = pattern.matcher(text);
        return matcher.find() ? Integer.parseInt(matcher.group(1)) : fallback;
    }

    private static double clamp(final double value, final double min, final double max) {
        return Math.max(min, Math.min(max, value));
    }

    private static String escapeJson(final String value) {
        return value == null ? "" : value
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
            .replace("\r", "\\r")
            .replace("\n", "\\n");
    }

    private static int regionIndex(final String region) {
        return switch (region.toLowerCase(Locale.ROOT)) {
            case "shanghai", "sh" -> 0;
            case "beijing", "bj" -> 1;
            case "hangzhou", "hz" -> 2;
            default -> 0;
        };
    }

    public record SimNode(
        String nodeId,
        String region,
        String location,
        String serviceRegion,
        int index,
        double cpu,
        double mipsPerPe,
        double totalMips,
        double memoryGb,
        double gpu,
        double gpuMemoryGb,
        double storageGb,
        double storageIops,
        double bandwidthMbps,
        double costPerTick,
        double reliability,
        double performanceFactor,
        double risk,
        String siteId,
        String powerProfileId,
        double idlePowerW,
        double maxPowerW,
        double gpuIdlePowerW,
        double gpuMaxPowerW,
        double pue,
        Map<Double, Double> carbonIntensityTrace,
        double baseCarbonIntensityGPerKwh
    ) {
        /** Backward-compatible constructor for the original four-resource example. */
        public SimNode(
            final String nodeId,
            final String region,
            final String location,
            final String serviceRegion,
            final int index,
            final double cpu,
            final double memoryGb,
            final double gpu,
            final double storageGb,
            final double bandwidthMbps,
            final double costPerTick,
            final double reliability,
            final double performanceFactor,
            final double risk
        ) {
            this(
                nodeId, region, location, serviceRegion, index, cpu, 0.0, 0.0,
                memoryGb, gpu, gpu * 16.0, storageGb, 0.0, bandwidthMbps,
                costPerTick, reliability, performanceFactor, risk,
                region + "-site", "legacy-power-profile", 0.0, 0.0, 0.0, 0.0,
                1.0, Map.of(), 0.0
            );
        }

        public double carbonIntensityAt(final double tick) {
            if (carbonIntensityTrace != null && !carbonIntensityTrace.isEmpty()) {
                final double dailyTick = Math.max(0.0, tick) % 24.0;
                double selectedTick = -1.0;
                double selectedValue = baseCarbonIntensityGPerKwh;
                for (final var entry : carbonIntensityTrace.entrySet()) {
                    if (entry.getKey() <= dailyTick && entry.getKey() >= selectedTick) {
                        selectedTick = entry.getKey();
                        selectedValue = entry.getValue();
                    }
                }
                if (selectedTick < 0.0) {
                    for (final var entry : carbonIntensityTrace.entrySet()) {
                        if (entry.getKey() > selectedTick) {
                            selectedTick = entry.getKey();
                            selectedValue = entry.getValue();
                        }
                    }
                }
                return Math.max(0.0, selectedValue);
            }
            final double diurnal = 1.0 + 0.18 * Math.sin((tick + index * 3.0) * Math.PI / 12.0);
            return Math.max(40.0, baseCarbonIntensityGPerKwh * diurnal);
        }
    }

    public record SimTask(
        String taskId,
        String taskType,
        double cpu,
        double requiredMips,
        double memoryGb,
        double gpu,
        double gpuMemoryGb,
        double storageGb,
        double storageIops,
        int estimatedDuration,
        int priority,
        double budget,
        int deadline,
        String sourceRegion,
        double inputSizeGb,
        double maxLatencyMs,
        double minBandwidthMbps,
        double networkSensitivity,
        double carbonBudgetG,
        double carbonPriority,
        double expectedCpuUtilization,
        boolean allowRegionShift,
        boolean allowTimeShift,
        int deferrableUntilTick,
        String batchId
    ) {
        /** Backward-compatible constructor for pre-batch CloudSim tasks. */
        public SimTask(
            final String taskId,
            final String taskType,
            final double cpu,
            final double memoryGb,
            final double gpu,
            final double storageGb,
            final int estimatedDuration,
            final int priority,
            final double budget,
            final int deadline,
            final String sourceRegion,
            final double inputSizeGb,
            final double maxLatencyMs,
            final double minBandwidthMbps,
            final double networkSensitivity
        ) {
            this(
                taskId, taskType, cpu, 0.0, memoryGb, gpu, gpu * 16.0,
                storageGb, 0.0, estimatedDuration, priority, budget, deadline,
                sourceRegion, inputSizeGb, maxLatencyMs, minBandwidthMbps,
                networkSensitivity, 1_000_000.0, 0.5, 0.5, true, false, 0, ""
            );
        }
    }

    public record NetworkPath(
        double latencyMs,
        double jitterMs,
        double bandwidthMbps,
        double bandwidthJitterMbps,
        double packetLoss,
        double pathReliability
    ) {
    }

    public record SchedulingResult(String status, String nodeId, String leaseTaskId, double score, String rawJson) {
        public boolean hasDecision() {
            return nodeId != null && !nodeId.isBlank() && (
                "leased".equalsIgnoreCase(status)
                    || "scheduled".equalsIgnoreCase(status)
                    || "committed".equalsIgnoreCase(status)
            );
        }
    }

    public record LeaseResult(String taskId, String nodeId, String rawJson, int estimatedDuration, double predictedCost) {
    }

    public record BatchPlanResult(
        String batchId,
        String planId,
        int resourceSnapshotVersion,
        String strategy,
        String rawJson
    ) {
    }

    public record SimTaskProgress(
        String nodeId,
        String taskId,
        String stage,
        String status,
        double progress,
        String message,
        double tick,
        double cpuUtilization,
        double memoryUtilization,
        double bandwidthUtilization,
        double storageUtilization
    ) {
    }

    public record SimTaskResult(
        String nodeId,
        String taskId,
        boolean success,
        double durationSeconds,
        String stdout,
        String stderr,
        int returnCode,
        double cost,
        double energyKwh,
        double computeCarbonG,
        double networkCarbonG,
        double queueWaitSeconds,
        double jctSeconds,
        double cpuUtilization,
        double memoryUtilization,
        double bandwidthUtilization,
        double storageUtilization
    ) {
        /** Backward-compatible constructor when execution telemetry is unavailable. */
        public SimTaskResult(
            final String nodeId,
            final String taskId,
            final boolean success,
            final double durationSeconds,
            final String stdout,
            final String stderr,
            final int returnCode,
            final double cost
        ) {
            this(
                nodeId, taskId, success, durationSeconds, stdout, stderr, returnCode, cost,
                0.0, 0.0, 0.0, 0.0, durationSeconds, 0.0, 0.0, 0.0, 0.0
            );
        }
    }
}
