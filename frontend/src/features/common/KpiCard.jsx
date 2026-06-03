import { Card, Progress, Statistic, Typography } from "@arco-design/web-react";
import clsx from "clsx";

export function KpiCard({ title, value, suffix, trend, progress, tone = "blue" }) {
  return (
    <Card className={clsx("tj-kpi-card", `tone-${tone}`)} bordered={false}>
      <Typography.Text type="secondary">{title}</Typography.Text>
      <div className="tj-kpi-value">
        <Statistic value={value} suffix={suffix} />
      </div>
      {progress !== undefined ? (
        <Progress percent={Math.round(Number(progress ?? 0) * 100)} showText={false} size="small" />
      ) : null}
      {trend ? <Typography.Text className="tj-kpi-trend">{trend}</Typography.Text> : null}
    </Card>
  );
}
