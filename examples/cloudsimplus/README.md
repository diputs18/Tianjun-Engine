# CloudSim Plus DCI 示例

本目录归档了用于生成 `data/dci_reference/` 中 DCI 拓扑感知训练数据的 CloudSim Plus 桥接文件。

将这些文件复制到 CloudSim Plus Examples 检出项目的对应位置，或与本地实验项目进行比较：

```text
src/main/java/org/cloudsimplus/examples/HuaweiDciTianjunExperiment.java
src/main/java/org/cloudsimplus/examples/tianjun/TianjunHttpBridge.java
src/main/resources/huawei-dci-reference.brite
```

该实验创建了 24 个模拟计算 VM，并将三个 Hermes 部署区域映射到各一个模拟物理接入点：

- `east`：北京/杭州，连接到 `DC1`
- `west`：成都/重庆，连接到 `DC2`
- `south`：广州/深圳，连接到 `DC3`

`DC1/DC2` 遵循项目 README 中描述的公开案例抽象。`DC3` 是用于三区域实验的可复现模拟扩展，不是声称的生产网络站点。
