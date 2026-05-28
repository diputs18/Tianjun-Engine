# CloudSim Plus DCI Example

This directory archives the CloudSim Plus bridge files used to generate the
DCI topology-aware training data in `data/dci_reference/`.

Copy these files into the matching locations of a CloudSim Plus Examples
checkout, or compare them with the local experiment project:

```text
src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java
src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java
src/main/resources/huawei-dci-reference.brite
```

The experiment creates 24 simulated compute VMs and maps the three Hermes
deployment regions to one simulated physical access point each:

- `east`: Beijing/Hangzhou, attached to `DC1`
- `west`: Chengdu/Chongqing, attached to `DC2`
- `south`: Guangzhou/Shenzhen, attached to `DC3`

`DC1/DC2` follow the public case abstraction described in the project README.
`DC3` is a reproducible simulation extension for the three-region experiment,
not a claimed production network site.
