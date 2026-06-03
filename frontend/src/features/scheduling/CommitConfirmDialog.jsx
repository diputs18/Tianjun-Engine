import { Button, Modal } from "@arco-design/web-react";
import { IconCheckCircle } from "@arco-design/web-react/icon";

export function CommitConfirmDialog({ policyId, visible, loading, onCancel, onConfirm }) {
  return (
    <Modal
      title="确认提交策略"
      visible={visible}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel} disabled={loading}>取消</Button>,
        <Button key="confirm" type="primary" icon={<IconCheckCircle />} loading={loading} onClick={onConfirm}>确认提交</Button>,
      ]}
    >
      <p className="tj-ai-confirm-text">
        此操作将正式下发策略 <b>{policyId}</b>。天钧要求在任务提交前必须经过一次显式按钮确认。
      </p>
    </Modal>
  );
}
