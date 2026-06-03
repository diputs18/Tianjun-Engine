import { Space, Typography } from "@arco-design/web-react";

export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="tj-page-header">
      <div>
        <Typography.Text className="tj-kicker">{eyebrow}</Typography.Text>
        <Typography.Title heading={2}>{title}</Typography.Title>
        {description ? <Typography.Paragraph>{description}</Typography.Paragraph> : null}
      </div>
      {actions ? <Space>{actions}</Space> : null}
    </div>
  );
}
