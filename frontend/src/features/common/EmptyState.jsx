import { Empty } from "@arco-design/web-react";

export function EmptyState({ description = "暂无数据" }) {
  return <Empty className="tj-empty" description={description} />;
}
