import { Button, Modal } from "@arco-design/web-react";
import { IconCheckCircle } from "@arco-design/web-react/icon";

export function CommitConfirmDialog({ policyId, visible, loading, onCancel, onConfirm }) {
  return (
    <Modal
      title="Commit policy"
      visible={visible}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel} disabled={loading}>Cancel</Button>,
        <Button key="confirm" type="primary" icon={<IconCheckCircle />} loading={loading} onClick={onConfirm}>Commit</Button>,
      ]}
    >
      <p className="tj-ai-confirm-text">
        This action dispatches policy <b>{policyId}</b>. Tianjun requires this explicit button confirmation before work can be submitted.
      </p>
    </Modal>
  );
}
