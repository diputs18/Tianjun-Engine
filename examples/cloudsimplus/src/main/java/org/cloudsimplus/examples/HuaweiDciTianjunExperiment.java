/*
 * Case-referenced DCI topology experiment for Tianjun Engine.
 *
 * The logical chain is abstracted from a public compute-network DCI case:
 * DC1 -> Border1 -> PE1 -> backbone P routers -> PE3 -> Border2 -> DC2,
 * plus a user access point connected at the destination-side PE. A simulated
 * DC3 access branch is added at PE3 so Tianjun can evaluate one access point
 * per Hermes deployment region.
 * Resource capacities and dynamic impairments are reproducible simulation
 * assumptions and are not vendor production telemetry.
 */
package org.cloudsimplus.examples;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.annotations.SerializedName;
import org.cloudsimplus.brokers.DatacenterBroker;
import org.cloudsimplus.brokers.DatacenterBrokerSimple;
import org.cloudsimplus.builders.tables.CloudletsTableBuilder;
import org.cloudsimplus.cloudlets.Cloudlet;
import org.cloudsimplus.cloudlets.CloudletSimple;
import org.cloudsimplus.core.CloudSimPlus;
import org.cloudsimplus.datacenters.Datacenter;
import org.cloudsimplus.datacenters.DatacenterSimple;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.LeaseResult;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.BatchPlanResult;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.NetworkPath;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.SimNode;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.SimTask;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.SimTaskProgress;
import org.cloudsimplus.examples.tianjun.TianjunHttpBridge.SimTaskResult;
import org.cloudsimplus.hosts.Host;
import org.cloudsimplus.hosts.HostSimple;
import org.cloudsimplus.listeners.EventInfo;
import org.cloudsimplus.network.topologies.BriteNetworkTopology;
import org.cloudsimplus.power.models.PowerModelHostSimple;
import org.cloudsimplus.resources.Pe;
import org.cloudsimplus.resources.PeSimple;
import org.cloudsimplus.utilizationmodels.UtilizationModelDynamic;
import org.cloudsimplus.vms.Vm;
import org.cloudsimplus.vms.VmSimple;

import java.io.BufferedWriter;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import java.util.Set;

/**
 * Runs a three-access-point DCI topology against the Tianjun HTTP control plane.
 *
 * <p>BRITE supplies the static DCI propagation graph used by CloudSim Plus.
 * Heartbeat path observations start from the graph-derived site-to-site delay,
 * then apply documented congestion and optional failure disturbances to produce
 * raw graph snapshots suitable for subsequent GNN dataset labeling.</p>
 */
public final class HuaweiDciTianjunExperiment {
    private static final String TOPOLOGY_FILE = "huawei-dci-reference.brite";
    private static final String POWER_PROFILE_FILE = "tianjun-power-profiles.json";
    private static final String CARBON_TRACE_FILE = "tianjun-carbon-intensity-trace.csv";
    private static final String DEFAULT_SERVER = "http://127.0.0.1:8024";
    private static final String[] REGIONS = {"dc1", "dc2", "dc3"};
    private static final String[] LOCATIONS = {"beijing", "hangzhou", "chengdu", "chongqing", "guangzhou", "shenzhen"};
    private static final String[] SERVICE_REGIONS = {"east", "east", "west", "west", "south", "south"};
    private static final int[] LOCATION_SITES = {0, 0, 1, 1, 2, 2};
    private static final int VMS_PER_LOCATION = 4;
    private static final int DEFAULT_CLOUDLETS = 36;
    private static final long DEFAULT_SEED = 20260527L;
    private static final double HEARTBEAT_INTERVAL_SECONDS = 2.0;
    private static final long LISTENER_POLL_MILLIS = 350L;
    private static final double LOCAL_FABRIC_LATENCY_MS = 0.8;
    private static final double LOCAL_FABRIC_BANDWIDTH_MBPS = 25_000.0;
    private static final double DCI_BOTTLENECK_BANDWIDTH_MBPS = 10_000.0;
    // Effective throughput used only by the control-plane preview contract.
    // It is calibrated against the fixed CloudSim workload below; actual JCT
    // and Makespan are always measured from completed Cloudlets.
    private static final double PREDICTION_EFFECTIVE_MIPS = 4_000.0;
    private static final double[] SITE_IDLE_POWER_W = {155.0, 148.0, 142.0};
    private static final double[] SITE_MAX_POWER_W = {430.0, 405.0, 390.0};
    private static final double[] SITE_PUE = {1.38, 1.28, 1.22};
    private static final double[] SITE_CARBON_G_PER_KWH = {560.0, 430.0, 310.0};

    private final CloudSimPlus simulation;
    private final DatacenterBroker broker;
    private final TianjunHttpBridge bridge;
    private final BriteNetworkTopology topology;
    private final List<Datacenter> datacenters;
    private final List<Vm> vmList;
    private final List<Cloudlet> cloudletList;
    private final Map<String, Vm> vmByNodeId;
    private final Map<String, SimNode> nodeById;
    private final Map<Long, SimTask> taskByCloudletId;
    private final Map<String, Long> cloudletIdByTaskId;
    private final Map<Long, String> selectedNodeByCloudletId;
    private final Map<Long, Vm> selectedVmByCloudletId;
    private final Set<Long> submittedCloudletIds;
    private final Set<Long> reportedResultCloudletIds;
    private final Random random;
    private final Gson gson;
    private final String disturbanceScenario;
    private final String experimentRunId;
    private final String batchStrategy;
    private final Map<Integer, PowerProfileConfig> powerProfilesBySite;
    private final Map<Integer, CarbonSiteConfig> carbonProfilesBySite;
    private final BufferedWriter snapshotWriter;
    private final Path metricsOutputPath;
    private final boolean listenAfterBatch;
    private String committedBatchId;
    private double lastHeartbeatTick = -1.0;

    public static void main(final String[] args) throws IOException {
        final String server = args.length > 0 ? args[0] : DEFAULT_SERVER;
        final String scenario = args.length > 1 ? args[1] : "normal";
        final int cloudlets = args.length > 2 ? Integer.parseInt(args[2]) : DEFAULT_CLOUDLETS;
        final long seed = args.length > 3 ? Long.parseLong(args[3]) : DEFAULT_SEED;
        final Path output = Path.of(args.length > 4 ? args[4] : "output/huawei-dci-topology-snapshots.jsonl");
        final boolean listenAfterBatch = args.length <= 5 || !"once".equalsIgnoreCase(args[5]);
        final String strategy = args.length > 6 ? args[6] : "B6-hierarchical-batch";
        new HuaweiDciTianjunExperiment(server, scenario, cloudlets, seed, output, listenAfterBatch, strategy).run();
    }

    private HuaweiDciTianjunExperiment(
        final String server,
        final String disturbanceScenario,
        final int cloudletCount,
        final long seed,
        final Path outputPath,
        final boolean listenAfterBatch,
        final String batchStrategy
    ) throws IOException {
        this.simulation = new CloudSimPlus();
        this.bridge = new TianjunHttpBridge(server);
        this.listenAfterBatch = listenAfterBatch;
        this.disturbanceScenario = disturbanceScenario.toLowerCase(Locale.ROOT);
        this.experimentRunId = "dci-" + this.disturbanceScenario + "-" + seed;
        this.batchStrategy = batchStrategy;
        this.random = new Random(seed);
        this.gson = new GsonBuilder().disableHtmlEscaping().create();
        this.powerProfilesBySite = loadPowerProfiles();
        this.carbonProfilesBySite = loadCarbonProfiles();
        this.vmByNodeId = new LinkedHashMap<>();
        this.nodeById = new LinkedHashMap<>();
        this.taskByCloudletId = new LinkedHashMap<>();
        this.cloudletIdByTaskId = new LinkedHashMap<>();
        this.selectedNodeByCloudletId = new LinkedHashMap<>();
        this.selectedVmByCloudletId = new LinkedHashMap<>();
        this.submittedCloudletIds = new HashSet<>();
        this.reportedResultCloudletIds = new HashSet<>();
        this.datacenters = createDatacenters();
        this.broker = new DatacenterBrokerSimple(simulation);
        this.topology = configureDciTopology();
        this.vmList = createVms();
        this.cloudletList = createCloudlets(cloudletCount);
        final Path parent = outputPath.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        this.snapshotWriter = Files.newBufferedWriter(outputPath.toAbsolutePath());
        this.metricsOutputPath = outputPath.toAbsolutePath().resolveSibling(
            outputPath.getFileName().toString().replaceFirst("\\.[^.]+$", "") + ".metrics.json"
        );
    }

    private void run() throws IOException {
        if (!bridge.isHealthy()) {
            snapshotWriter.close();
            throw new IllegalStateException("Tianjun control plane is not reachable at the configured server.");
        }

        broker.setDatacenterMapper((lastDatacenter, vm) -> datacenters.get(siteIndexForVm(vm)));
        broker.submitVmList(vmList);
        registerTianjunNodes();
        submitBatchToTianjun();
        pollLeasesAndSubmitCloudlets(0.0);
        simulation.addOnClockTickListener(this::onClockTick);

        writeSnapshot(0.0, "registered");
        try {
            simulation.start();
        } finally {
            sendHeartbeats(simulation.clock());
            reportResults();
            writeSnapshot(simulation.clock(), "finished");
            writeBatchMetrics();
            snapshotWriter.close();
        }

        final var finished = broker.getCloudletFinishedList();
        System.out.printf("=== Huawei-reference DCI Tianjun experiment (%s) ===%n", disturbanceScenario);
        System.out.printf("Topology: DC1 -> Border1 -> PE1 -> IPCORE -> PE3 -> Border2 -> DC2, plus PE3 -> Border3 -> DC3%n");
        System.out.printf("Simulation nodes: %d, submitted tasks: %d, finished: %d%n", vmList.size(), cloudletList.size(), finished.size());
        System.out.printf("Max cross-site propagation baseline: %.3f ms, DCI bottleneck: %.0f Mbps%n", maxCrossSiteBaseLatencyMs(), DCI_BOTTLENECK_BANDWIDTH_MBPS);
        new CloudletsTableBuilder(finished).build();
        if (listenAfterBatch) {
            listenForExternalLeases();
        }
    }

    private List<Datacenter> createDatacenters() {
        final var list = new ArrayList<Datacenter>();
        for (int site = 0; site < REGIONS.length; site++) {
            final var dc = new DatacenterSimple(simulation, createHosts(site));
            dc.setName("DC" + (site + 1));
            dc.setSchedulingInterval(1.0);
            list.add(dc);
        }
        return list;
    }

    private List<Host> createHosts(final int site) {
        final var hosts = new ArrayList<Host>();
        final PowerProfileConfig powerProfile = powerProfileForSite(site);
        for (int index = 0; index < 3; index++) {
            final int pes = 32;
            final long mips = site == 0 ? 2400L : site == 1 ? 2250L : 2200L;
            final long ramMb = 131_072L;
            final long bandwidthMbps = 120_000L;
            final long storageMb = 4_000_000L;
            final var peList = new ArrayList<Pe>();
            for (int pe = 0; pe < pes; pe++) {
                peList.add(new PeSimple(mips));
            }
            final var host = new HostSimple(ramMb, bandwidthMbps, storageMb, peList);
            host.setPowerModel(new PowerModelHostSimple(
                powerProfile.maxPowerW,
                powerProfile.idlePowerW
            ));
            hosts.add(host);
        }
        return hosts;
    }

    private BriteNetworkTopology configureDciTopology() {
        final var dciTopology = BriteNetworkTopology.getInstance(TOPOLOGY_FILE);
        simulation.setNetworkTopology(dciTopology);
        // BRITE node map: 0 DC1, 1 Border1, 2 PE1, 3/4 P routers,
        // 5 PE3, 6 Border2, 7 DC2, 8 user access, 9 Border3, 10 DC3.
        dciTopology.mapNode(datacenters.get(0), 0);
        dciTopology.mapNode(datacenters.get(1), 7);
        dciTopology.mapNode(datacenters.get(2), 10);
        dciTopology.mapNode(broker, 8);
        return dciTopology;
    }

    private List<Vm> createVms() {
        final var result = new ArrayList<Vm>();
        for (int locationIndex = 0; locationIndex < LOCATIONS.length; locationIndex++) {
            final int site = LOCATION_SITES[locationIndex];
            for (int index = 0; index < VMS_PER_LOCATION; index++) {
                final int pes = 4 + (index % 2) * 4;
                final double mips = site == 0 ? 2200.0 : site == 1 ? 2120.0 : 2050.0;
                final var vm = new VmSimple(mips, pes)
                    .setRam(16_384L + (index % 2) * 16_384L)
                    .setBw(20_000L)
                    .setSize(200_000L)
                    .setDescription("dci-" + REGIONS[site] + "-" + LOCATIONS[locationIndex] + "-vm-" + index);
                result.add(vm);
                vmByNodeId.put(vm.getDescription(), vm);
            }
        }
        return result;
    }

    private List<Cloudlet> createCloudlets(final int count) {
        final var result = new ArrayList<Cloudlet>();
        for (int index = 0; index < count; index++) {
            final var cloudlet = new CloudletSimple(index, 8_000L + index % 6 * 2_000L, 1 + index % 4);
            cloudlet.setFileSize(512L + index % 4 * 128L)
                .setOutputSize(1_024L)
                .setUtilizationModelCpu(new UtilizationModelDynamic(0.24 + random.nextDouble() * 0.18))
                .setUtilizationModelRam(new UtilizationModelDynamic(0.08 + random.nextDouble() * 0.12))
                .setUtilizationModelBw(new UtilizationModelDynamic(0.04 + random.nextDouble() * 0.10));
            result.add(cloudlet);
        }
        return result;
    }

    private void registerTianjunNodes() {
        for (int index = 0; index < vmList.size(); index++) {
            final var node = simNodeForVm(vmList.get(index), index);
            nodeById.put(node.nodeId(), node);
        }
        bridge.registerTopology(gson.toJson(topologyRegistration()));
        for (final var node : nodeById.values()) {
            bridge.registerNode(node, observedPaths(node, 0.0, 0.0));
            bridge.heartbeat(node, 0.0, 0.0, 0.0, 0.0, observedPaths(node, 0.0, 0.0));
        }
        System.out.printf("Registered physical DCI topology and %d attached compute nodes with topology-derived paths.%n", nodeById.size());
    }

    private void submitBatchToTianjun() {
        for (int index = 0; index < cloudletList.size(); index++) {
            final Cloudlet cloudlet = cloudletList.get(index);
            final SimTask task = taskForCloudlet(cloudlet, index);
            taskByCloudletId.put(cloudlet.getId(), task);
            cloudletIdByTaskId.put(task.taskId(), cloudlet.getId());
        }
        final BatchPlanResult batchPlan = bridge.commitTaskBatch(
            experimentRunId + "-batch",
            "CloudSim DCI " + disturbanceScenario + " " + batchStrategy,
            new ArrayList<>(taskByCloudletId.values()),
            batchStrategy
        );
        committedBatchId = batchPlan.batchId();
        System.out.printf(
            "Imported and committed CloudSim batch %s using %s (plan %s, snapshot %d), tasks: %d.%n",
            batchPlan.batchId(),
            batchPlan.strategy(),
            batchPlan.planId(),
            batchPlan.resourceSnapshotVersion(),
            taskByCloudletId.size()
        );
    }

    private void writeBatchMetrics() throws IOException {
        if (committedBatchId == null || committedBatchId.isBlank()) {
            return;
        }
        final String metrics = bridge.getBatchActualMetrics(committedBatchId);
        Files.writeString(metricsOutputPath, metrics, StandardCharsets.UTF_8);
        System.out.printf("Wrote actual CloudSim batch metrics to %s.%n", metricsOutputPath);
    }

    private int pollLeasesAndSubmitCloudlets(final double tick) {
        int mapped = 0;
        broker.setVmMapper(cloudlet -> selectedVmByCloudletId.getOrDefault(cloudlet.getId(), Vm.NULL));
        for (final var node : nodeById.values()) {
            final LeaseResult lease;
            try {
                lease = bridge.requestLease(node.nodeId());
            } catch (IllegalStateException exception) {
                System.err.printf(
                    "WARN %.2f: Tianjun lease polling failed for %s; CloudSim will keep running and retry later. %s%n",
                    tick,
                    node.nodeId(),
                    exception.getMessage()
                );
                continue;
            }
            if (lease == null) {
                continue;
            }
            final Long cloudletId = cloudletIdByTaskId.get(lease.taskId());
            if (cloudletId == null) {
                executeExternalLease(lease, node, tick);
                continue;
            }
            final Cloudlet cloudlet = cloudletById(cloudletId);
            final Vm selectedVm = vmByNodeId.get(lease.nodeId());
            if (cloudlet == null || selectedVm == null || selectedVm == Vm.NULL || submittedCloudletIds.contains(cloudletId)) {
                continue;
            }
            selectedVmByCloudletId.put(cloudletId, selectedVm);
            selectedNodeByCloudletId.put(cloudletId, lease.nodeId());
            submittedCloudletIds.add(cloudletId);
            broker.submitCloudletList(List.of(cloudlet));
            reportProgress(cloudlet, tick, "leased", 0.0, "CloudSim lease acquired; cloudlet submitted to VM.");
            mapped++;
        }
        broker.setVmMapper(cloudlet -> selectedVmByCloudletId.getOrDefault(cloudlet.getId(), Vm.NULL));
        if (mapped > 0) {
            System.out.printf("Tianjun leased and submitted %d new DCI tasks; total submitted: %d/%d.%n", mapped, submittedCloudletIds.size(), cloudletList.size());
        }
        return mapped;
    }

    private void listenForExternalLeases() {
        System.out.println("Tianjun CloudSim listener is running. Press Ctrl+C or stop the IntelliJ run to exit.");
        while (true) {
            final double tick = Math.max(simulation.clock(), System.currentTimeMillis() / 1000.0);
            sendSyntheticHeartbeats(tick);
            int executed = 0;
            for (final var node : nodeById.values()) {
                final LeaseResult lease;
                try {
                    lease = bridge.requestLease(node.nodeId());
                } catch (IllegalStateException exception) {
                    System.err.printf(
                        "WARN listener: lease polling failed for %s; retrying. %s%n",
                        node.nodeId(),
                        exception.getMessage()
                    );
                    continue;
                }
                if (lease == null) {
                    continue;
                }
                final Long localCloudletId = cloudletIdByTaskId.get(lease.taskId());
                if (localCloudletId != null) {
                    continue;
                }
                executeExternalLease(lease, node, tick);
                executed++;
            }
            if (executed > 0) {
                System.out.printf("Tianjun listener executed %d externally submitted task(s).%n", executed);
            }
            try {
                Thread.sleep(LISTENER_POLL_MILLIS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    private void executeExternalLease(final LeaseResult lease, final SimNode node, final double tick) {
        final double duration = externalDurationSeconds(lease);
        reportExternalProgress(node.nodeId(), lease.taskId(), tick, "leased", 0.05, "Lease acquired by CloudSim listener.");
        reportExternalProgress(node.nodeId(), lease.taskId(), tick + duration * 0.45, "executing", 0.65, "CloudSim listener executing external task.");
        sleepQuietly(Math.min(450L, Math.max(120L, Math.round(duration * 120.0))));
        final double energyKwh = incrementalEnergyKwh(node, duration, 0.55);
        final double computeCarbonG = energyKwh * node.pue() * node.carbonIntensityAt(tick);
        reportResultWithRetry(new SimTaskResult(
            node.nodeId(),
            lease.taskId(),
            true,
            duration,
            "CloudSim listener completed externally submitted Tianjun task.",
            "",
            0,
            Math.min(lease.predictedCost(), duration * node.costPerTick()),
            energyKwh,
            computeCarbonG,
            0.0,
            0.0,
            duration,
            0.55,
            0.30,
            0.20,
            0.0
        ));
    }

    private double externalDurationSeconds(final LeaseResult lease) {
        final int estimated = lease.estimatedDuration();
        return Math.max(1.0, Math.min(4.0, estimated <= 0 ? 2.0 : Math.ceil(estimated / 3.0)));
    }

    private void reportExternalProgress(
        final String nodeId,
        final String taskId,
        final double tick,
        final String stage,
        final double progress,
        final String message
    ) {
        try {
            bridge.reportProgress(new SimTaskProgress(
                nodeId,
                taskId,
                stage,
                "running",
                progress,
                message,
                tick,
                0.18 + progress * 0.25,
                0.12 + progress * 0.18,
                0.08 + progress * 0.16,
                0.0
            ));
        } catch (IllegalStateException exception) {
            System.err.printf("WARN listener: progress report failed for task %s. %s%n", taskId, exception.getMessage());
        }
    }

    private void sendSyntheticHeartbeats(final double tick) {
        for (final var node : nodeById.values()) {
            final double wave = 0.5 + Math.sin(tick * 0.17 + node.index()) * 0.5;
            bridge.tryHeartbeat(
                node,
                tick,
                0.08 + wave * 0.18,
                0.10 + wave * 0.12,
                0.04 + wave * 0.10,
                observedPaths(node, tick, 0.04 + wave * 0.10)
            );
        }
    }

    private static void sleepQuietly(final long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    private void onClockTick(final EventInfo event) {
        final double tick = event.getTime();
        if (lastHeartbeatTick >= 0.0 && tick - lastHeartbeatTick < HEARTBEAT_INTERVAL_SECONDS) {
            return;
        }
        sendHeartbeats(tick);
        pollLeasesAndSubmitCloudlets(tick);
        reportActiveProgress(tick);
        try {
            writeSnapshot(tick, "running");
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot write topology snapshot.", exception);
        }
    }

    private void sendHeartbeats(final double tick) {
        lastHeartbeatTick = tick;
        for (final var vm : vmList) {
            final var node = nodeById.get(vm.getDescription());
            final double cpu = vm.getCpuPercentUtilization();
            final double ram = vm.getRam().getPercentUtilization();
            final double bw = vm.getBw().getPercentUtilization();
            bridge.tryHeartbeat(node, tick, cpu, ram, bw, observedPaths(node, tick, bw));
        }
    }

    private void reportResults() {
        for (final var cloudlet : broker.getCloudletFinishedList()) {
            if (reportedResultCloudletIds.contains(cloudlet.getId())) {
                continue;
            }
            final var task = taskByCloudletId.get(cloudlet.getId());
            final String nodeId = selectedNodeByCloudletId.get(cloudlet.getId());
            if (task == null || nodeId == null) {
                continue;
            }
            reportProgress(cloudlet, simulation.clock(), "finished", 1.0, "CloudSim cloudlet finished; reporting final result.");
            final double duration = Math.max(1.0, cloudlet.getFinishTime() - cloudlet.getStartTime());
            final SimNode node = nodeById.get(nodeId);
            final double sampleTime = Math.max(0.0, cloudlet.getStartTime() + duration / 2.0);
            final double cpuUtilization = clamp(
                cloudlet.getUtilizationModelCpu().getUtilization(sampleTime),
                0.0,
                1.0
            );
            final double memoryUtilization = clamp(
                cloudlet.getUtilizationModelRam().getUtilization(sampleTime),
                0.0,
                1.0
            );
            final double bandwidthUtilization = clamp(
                cloudlet.getUtilizationModelBw().getUtilization(sampleTime),
                0.0,
                1.0
            );
            final double energyKwh = incrementalEnergyKwh(node, duration, cpuUtilization);
            final double computeCarbonG = energyKwh * node.pue() * node.carbonIntensityAt(cloudlet.getStartTime());
            final double networkCarbonG = networkCarbonG(task, node);
            final var result = new SimTaskResult(
                nodeId,
                task.taskId(),
                cloudlet.isFinished(),
                duration,
                "Huawei-reference DCI CloudSim cloudlet completed.",
                "",
                cloudlet.isFinished() ? 0 : 1,
                duration * node.costPerTick(),
                energyKwh,
                computeCarbonG,
                networkCarbonG,
                Math.max(0.0, cloudlet.getStartTime()),
                Math.max(duration, cloudlet.getFinishTime()),
                cpuUtilization,
                memoryUtilization,
                bandwidthUtilization,
                task.storageGb() / Math.max(1.0, node.storageGb())
            );
            if (reportResultWithRetry(result)) {
                reportedResultCloudletIds.add(cloudlet.getId());
            }
        }
    }

    private void reportActiveProgress(final double tick) {
        for (final var cloudlet : cloudletList) {
            if (!submittedCloudletIds.contains(cloudlet.getId()) || reportedResultCloudletIds.contains(cloudlet.getId())) {
                continue;
            }
            if (cloudlet.isFinished()) {
                continue;
            }
            final double start = Math.max(0.0, cloudlet.getStartTime());
            final SimTask task = taskByCloudletId.get(cloudlet.getId());
            if (task == null) {
                continue;
            }
            final double elapsed = Math.max(0.0, tick - start);
            final double progress = Math.min(0.98, elapsed / Math.max(1.0, task.estimatedDuration()));
            reportProgress(cloudlet, tick, "executing", progress, "CloudSim cloudlet execution in progress.");
        }
    }

    private void reportProgress(
        final Cloudlet cloudlet,
        final double tick,
        final String stage,
        final double progress,
        final String message
    ) {
        final SimTask task = taskByCloudletId.get(cloudlet.getId());
        final String nodeId = selectedNodeByCloudletId.get(cloudlet.getId());
        final Vm vm = selectedVmByCloudletId.get(cloudlet.getId());
        if (task == null || nodeId == null || vm == null || vm == Vm.NULL) {
            return;
        }
        final var progressEvent = new SimTaskProgress(
            nodeId,
            task.taskId(),
            stage,
            cloudlet.isFinished() ? "succeeded" : "running",
            progress,
            message,
            tick,
            vm.getCpuPercentUtilization(),
            vm.getRam().getPercentUtilization(),
            vm.getBw().getPercentUtilization(),
            0.0
        );
        try {
            bridge.reportProgress(progressEvent);
        } catch (IllegalStateException exception) {
            System.err.printf(
                "WARN %.2f: Tianjun progress report failed for task %s; final result will still be attempted. %s%n",
                tick,
                task.taskId(),
                exception.getMessage()
            );
        }
    }

    private boolean reportResultWithRetry(final SimTaskResult result) {
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                bridge.reportResult(result);
                return true;
            } catch (IllegalStateException exception) {
                System.err.printf(
                    "WARN %.2f: Tianjun result report failed for task %s, attempt %d/3. %s%n",
                    simulation.clock(),
                    result.taskId(),
                    attempt,
                    exception.getMessage()
                );
                if (attempt < 3) {
                    try {
                        Thread.sleep(250L * attempt);
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                        return false;
                    }
                }
            }
        }
        return false;
    }

    private Cloudlet cloudletById(final long cloudletId) {
        for (final var cloudlet : cloudletList) {
            if (cloudlet.getId() == cloudletId) {
                return cloudlet;
            }
        }
        return null;
    }

    private SimNode simNodeForVm(final Vm vm, final int index) {
        final int locationIndex = index / VMS_PER_LOCATION;
        final int site = LOCATION_SITES[locationIndex];
        final double gpuCount = gpuCapacityForNode(site, index);
        final PowerProfileConfig powerProfile = powerProfileForSite(site);
        final CarbonSiteConfig carbonProfile = carbonProfileForSite(site);
        return new SimNode(
            vm.getDescription(),
            REGIONS[site],
            LOCATIONS[locationIndex],
            SERVICE_REGIONS[locationIndex],
            index,
            vm.getPesNumber(),
            vm.getMips(),
            vm.getPesNumber() * vm.getMips(),
            vm.getRam().getCapacity() / 1024.0,
            gpuCount,
            gpuCount * 16.0,
            vm.getStorage().getCapacity() / 1024.0,
            18_000.0 + site * 2_000.0,
            vm.getBw().getCapacity(),
            1.10 + site * 0.08 + (index % VMS_PER_LOCATION) * 0.04,
            0.993 - site * 0.002,
            site == 0 ? 1.10 : 1.04,
            site == 0 ? 0.06 : 0.09,
            "site-" + (site + 1),
            powerProfile.profileId,
            powerProfile.idlePowerW,
            powerProfile.maxPowerW,
            powerProfile.gpuIdlePowerW,
            powerProfile.gpuMaxPowerW,
            carbonProfile.pue,
            carbonProfile.trace,
            carbonProfile.trace.getOrDefault(0.0, SITE_CARBON_G_PER_KWH[site])
        );
    }

    private Map<Integer, PowerProfileConfig> loadPowerProfiles() throws IOException {
        final Map<Integer, PowerProfileConfig> result = new LinkedHashMap<>();
        try (final var stream = HuaweiDciTianjunExperiment.class.getClassLoader().getResourceAsStream(POWER_PROFILE_FILE)) {
            if (stream == null) {
                return result;
            }
            final var document = gson.fromJson(
                new InputStreamReader(stream, StandardCharsets.UTF_8),
                PowerProfileDocument.class
            );
            if (document != null && document.profiles != null) {
                for (int index = 0; index < document.profiles.size(); index++) {
                    result.put(index, document.profiles.get(index));
                }
            }
        }
        return result;
    }

    private Map<Integer, CarbonSiteConfig> loadCarbonProfiles() throws IOException {
        final Map<Integer, CarbonSiteConfig> result = new LinkedHashMap<>();
        try (final var stream = HuaweiDciTianjunExperiment.class.getClassLoader().getResourceAsStream(CARBON_TRACE_FILE)) {
            if (stream == null) {
                return result;
            }
            try (final var reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                boolean header = true;
                while ((line = reader.readLine()) != null) {
                    if (header) {
                        header = false;
                        continue;
                    }
                    final String[] fields = line.trim().split(",");
                    if (fields.length < 5 || !fields[0].startsWith("site-")) {
                        continue;
                    }
                    final int site = Integer.parseInt(fields[0].substring("site-".length())) - 1;
                    final double tick = Double.parseDouble(fields[2]);
                    final double intensity = Double.parseDouble(fields[3]);
                    final double pue = Double.parseDouble(fields[4]);
                    result.computeIfAbsent(site, ignored -> new CarbonSiteConfig(pue)).trace.put(tick, intensity);
                }
            }
        }
        return result;
    }

    private PowerProfileConfig powerProfileForSite(final int site) {
        return powerProfilesBySite.getOrDefault(
            site,
            new PowerProfileConfig(
                "host-profile-" + (site + 1),
                SITE_IDLE_POWER_W[site],
                SITE_MAX_POWER_W[site],
                35.0,
                300.0
            )
        );
    }

    private CarbonSiteConfig carbonProfileForSite(final int site) {
        final CarbonSiteConfig configured = carbonProfilesBySite.get(site);
        if (configured != null) {
            return configured;
        }
        final CarbonSiteConfig fallback = new CarbonSiteConfig(SITE_PUE[site]);
        fallback.trace.put(0.0, SITE_CARBON_G_PER_KWH[site]);
        return fallback;
    }

    private static final class PowerProfileDocument {
        private List<PowerProfileConfig> profiles;
    }

    private static final class PowerProfileConfig {
        @SerializedName("profile_id")
        private String profileId;
        @SerializedName("idle_power_w")
        private double idlePowerW;
        @SerializedName("max_power_w")
        private double maxPowerW;
        @SerializedName("gpu_idle_power_w")
        private double gpuIdlePowerW;
        @SerializedName("gpu_max_power_w")
        private double gpuMaxPowerW;

        private PowerProfileConfig(
            final String profileId,
            final double idlePowerW,
            final double maxPowerW,
            final double gpuIdlePowerW,
            final double gpuMaxPowerW
        ) {
            this.profileId = profileId;
            this.idlePowerW = idlePowerW;
            this.maxPowerW = maxPowerW;
            this.gpuIdlePowerW = gpuIdlePowerW;
            this.gpuMaxPowerW = gpuMaxPowerW;
        }
    }

    private static final class CarbonSiteConfig {
        private final double pue;
        private final Map<Double, Double> trace = new LinkedHashMap<>();

        private CarbonSiteConfig(final double pue) {
            this.pue = pue;
        }
    }

    private double gpuCapacityForNode(final int site, final int index) {
        final double siteBonus = site == 0 ? 1.0 : 0.0;
        final double anchorBonus = index % VMS_PER_LOCATION == 0 ? 1.0 : 0.0;
        return 1.0 + siteBonus + anchorBonus;
    }

    private SimTask taskForCloudlet(final Cloudlet cloudlet, final int index) {
        final String sourceRegion = REGIONS[index % REGIONS.length];
        final boolean gpuAccelerated = index % 6 == 0 || index % 6 == 3;
        return new SimTask(
            experimentRunId + "-task-" + cloudlet.getId(),
            gpuAccelerated ? "inference" : index % 3 == 1 ? "analytics" : "batch_cpu",
            Math.max(1.0, cloudlet.getPesNumber()),
            Math.max(1.0, cloudlet.getPesNumber()) * 2_000.0,
            2.0 + index % 4 * 2.0,
            gpuAccelerated ? 1.0 : 0.0,
            gpuAccelerated ? 8.0 : 0.0,
            Math.max(1.0, cloudlet.getFileSize() / 1024.0),
            1_500.0 + index % 4 * 500.0,
            Math.max(
                1,
                (int) Math.ceil(
                    cloudlet.getLength()
                        / (PREDICTION_EFFECTIVE_MIPS
                        * Math.max(0.05, cloudlet.getUtilizationModelCpu().getUtilization(0.0)))
                )
            ),
            5 + index % 5,
            220.0,
            180,
            sourceRegion,
            0.5 + index % 4 * 0.4,
            sourceRegion.equals("dc1") ? 25.0 : sourceRegion.equals("dc2") ? 28.0 : 30.0,
            500.0,
            0.55 + index % 4 * 0.10,
            12.0,
            0.65,
            cloudlet.getUtilizationModelCpu().getUtilization(0.0),
            true,
            false,
            0,
            experimentRunId + "-batch"
        );
    }

    private double incrementalEnergyKwh(final SimNode node, final double durationSeconds, final double utilization) {
        final double incrementalPowerW = Math.max(0.0, node.maxPowerW() - node.idlePowerW()) * clamp(utilization, 0.0, 1.0);
        return incrementalPowerW * durationSeconds / 3_600_000.0;
    }

    private double networkCarbonG(final SimTask task, final SimNode node) {
        if (task.sourceRegion().equals(node.region())) {
            return 0.0;
        }
        final double networkEnergyKwh = task.inputSizeGb() * 0.00008;
        return networkEnergyKwh * node.carbonIntensityAt(simulation.clock());
    }

    private Map<String, NetworkPath> observedPaths(final SimNode node, final double tick, final double bandwidthUtilization) {
        final var paths = new LinkedHashMap<String, NetworkPath>();
        for (final String sourceRegion : REGIONS) {
            final boolean crossSite = !sourceRegion.equals(node.region());
            final double baselineLatency = crossSite ? siteToSiteBaseLatencyMs(sourceRegion, node.region()) : LOCAL_FABRIC_LATENCY_MS;
            final double baselineBandwidth = crossSite ? DCI_BOTTLENECK_BANDWIDTH_MBPS : LOCAL_FABRIC_BANDWIDTH_MBPS;
            final double pressure = clamp(bandwidthUtilization, 0.0, 1.0);
            final boolean degraded = crossSite && isDciDegraded(tick);
            final double periodicVariation = Math.abs(Math.sin(tick * 0.13 + node.index() * 0.27));
            final double latency = baselineLatency * (1.0 + pressure * 0.32) + periodicVariation * 1.2 + (degraded ? 16.0 : 0.0);
            final double jitter = 0.35 + periodicVariation * 0.8 + pressure * 2.5 + (degraded ? 7.0 : 0.0);
            final double bandwidth = Math.max(200.0, baselineBandwidth * (1.0 - pressure * 0.38) * (degraded ? 0.32 : 1.0));
            final double bandwidthVariation = Math.max(
                25.0,
                bandwidth * (0.03 + pressure * 0.12 + (degraded ? 0.18 : 0.0))
            );
            final double loss = clamp(0.0005 + pressure * 0.0045 + (degraded ? 0.035 : 0.0), 0.0, 0.20);
            paths.put(sourceRegion, new NetworkPath(
                latency,
                jitter,
                bandwidth,
                bandwidthVariation,
                loss,
                clamp(0.999 - loss * 1.7, 0.45, 0.999)
            ));
        }
        return paths;
    }

    private double siteToSiteBaseLatencyMs(final String sourceRegion, final String targetRegion) {
        final int sourceIndex = siteIndexForRegion(sourceRegion);
        final int targetIndex = siteIndexForRegion(targetRegion);
        return Math.max(1.0, topology.getDelay(datacenters.get(sourceIndex), datacenters.get(targetIndex)) * 1000.0);
    }

    private double maxCrossSiteBaseLatencyMs() {
        double maxLatency = 0.0;
        for (final String sourceRegion : REGIONS) {
            for (final String targetRegion : REGIONS) {
                if (!sourceRegion.equals(targetRegion)) {
                    maxLatency = Math.max(maxLatency, siteToSiteBaseLatencyMs(sourceRegion, targetRegion));
                }
            }
        }
        return maxLatency;
    }

    private boolean isDciDegraded(final double tick) {
        if (disturbanceScenario.contains("fault-active")) {
            return true;
        }
        return disturbanceScenario.contains("fault") && tick >= 18.0 && tick < 48.0;
    }

    private int siteIndexForVm(final Vm vm) {
        if (vm.getDescription().contains("-dc3-")) {
            return 2;
        }
        return vm.getDescription().contains("-dc2-") ? 1 : 0;
    }

    private int siteIndexForRegion(final String region) {
        for (int index = 0; index < REGIONS.length; index++) {
            if (REGIONS[index].equals(region)) {
                return index;
            }
        }
        throw new IllegalArgumentException("Unknown DCI region: " + region);
    }

    private void writeSnapshot(final double tick, final String phase) throws IOException {
        final var sample = new LinkedHashMap<String, Object>();
        sample.put("scenario", "huawei_reference_dci");
        sample.put("experiment_run_id", experimentRunId);
        sample.put("disturbance", disturbanceScenario);
        sample.put("phase", phase);
        sample.put("tick_seconds", tick);
        sample.put("provenance", provenance());
        sample.put("topology_id", "huawei_public_case_reference_dci_v1");
        sample.put("topology_nodes", topologyNodeNames());
        sample.put("topology_edges", topologyEdges());
        sample.put("compute_attachments", topologyRegistration().get("compute_attachments"));
        final var observations = new ArrayList<Map<String, Object>>();
        for (final var vm : vmList) {
            final var node = nodeById.get(vm.getDescription());
            final var item = new LinkedHashMap<String, Object>();
            item.put("node_id", node.nodeId());
            item.put("region", node.region());
            item.put("location", node.location());
            item.put("service_region", node.serviceRegion());
            item.put("cpu_utilization", vm.getCpuPercentUtilization());
            item.put("memory_utilization", vm.getRam().getPercentUtilization());
            item.put("bandwidth_utilization", vm.getBw().getPercentUtilization());
            item.put("network_paths", observedPaths(node, tick, vm.getBw().getPercentUtilization()));
            observations.add(item);
        }
        sample.put("compute_nodes", observations);
        sample.put("dci_degraded", isDciDegraded(tick));
        snapshotWriter.write(gson.toJson(sample));
        snapshotWriter.newLine();
        snapshotWriter.flush();
    }

    private List<Map<String, Object>> topologyEdges() {
        return List.of(
            edge("DC1", "Border1", 0.5, 40_000.0),
            edge("Border1", "PE1", 0.7, 40_000.0),
            edge("PE1", "P-Core-A", 1.2, 20_000.0),
            edge("P-Core-A", "P-Core-B", 6.0, 10_000.0),
            edge("P-Core-B", "PE3", 6.0, 10_000.0),
            edge("PE3", "Border2", 1.2, 20_000.0),
            edge("Border2", "DC2", 0.7, 40_000.0),
            edge("User-Access", "PE3", 3.0, 10_000.0),
            edge("PE3", "Border3", 1.0, 20_000.0),
            edge("Border3", "DC3", 0.7, 40_000.0)
        );
    }

    private List<String> topologyNodeNames() {
        return List.of("DC1", "Border1", "PE1", "P-Core-A", "P-Core-B", "PE3", "Border2", "DC2", "User-Access", "Border3", "DC3");
    }

    private Map<String, Object> topologyRegistration() {
        final var payload = new LinkedHashMap<String, Object>();
        payload.put("topology_id", "huawei_public_case_reference_dci_v1");
        payload.put("topology_nodes", topologyNodeNames());
        payload.put("topology_edges", topologyEdges());
        final var attachments = new LinkedHashMap<String, String>();
        for (final var node : nodeById.values()) {
            attachments.put(node.nodeId(), "DC" + (siteIndexForRegion(node.region()) + 1));
        }
        payload.put("compute_attachments", attachments);
        payload.put("provenance", provenance());
        return payload;
    }

    private Map<String, Object> provenance() {
        final var value = new LinkedHashMap<String, Object>();
        value.put("structure_status", "public_case_abstraction");
        value.put("numeric_parameter_status", "calibrated_simulation_assumptions_not_vendor_telemetry");
        value.put("compute_node_status", "cloudsimplus_vm_resources_not_physical_inventory");
        value.put("location_status", "named_simulation_placement_labels_not_vendor_disclosed_sites");
        value.put("service_region_status", "three_simulated_deployment_zones_each_bound_to_one_simulated_access_point");
        value.put("description", "DCI structure follows the public case diagram; DC3 is a reproducible simulation branch for one-region-one-access-point evaluation. Named city placement, capacities and impairment dynamics are experimental values.");
        return value;
    }

    private Map<String, Object> edge(final String source, final String target, final double delayMs, final double bandwidthMbps) {
        final var edge = new LinkedHashMap<String, Object>();
        edge.put("source", source);
        edge.put("target", target);
        edge.put("propagation_delay_ms", delayMs);
        edge.put("bandwidth_mbps", bandwidthMbps);
        return edge;
    }

    private static double clamp(final double value, final double min, final double max) {
        return Math.max(min, Math.min(max, value));
    }
}
