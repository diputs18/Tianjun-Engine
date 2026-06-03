export function SectionTitle({ index, title, children, compact = false }) {
  return (
    <div className={`section-title${compact ? " compact" : ""}`}>
      <span>{index}</span>
      {children ? (
        <div>
          <h2>{title}</h2>
          {children}
        </div>
      ) : (
        <h2>{title}</h2>
      )}
    </div>
  );
}
