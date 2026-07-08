export default function FilterBar({ books, genre, onGenre, query, onQuery }) {
  const counts = new Map();
  for (const b of books) {
    const g = b.genre || "Uncategorized";
    counts.set(g, (counts.get(g) || 0) + 1);
  }
  const genres = [...counts.keys()].sort();

  return (
    <div style={styles.bar}>
      <input
        style={styles.search}
        type="search"
        placeholder="Search title or author…"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
      <div style={styles.chips}>
        <Chip
          label={`All (${books.length})`}
          active={genre === null}
          onClick={() => onGenre(null)}
        />
        {genres.map((g) => (
          <Chip
            key={g}
            label={`${g} (${counts.get(g)})`}
            active={genre === g}
            onClick={() => onGenre(genre === g ? null : g)}
          />
        ))}
      </div>
    </div>
  );
}

function Chip({ label, active, onClick }) {
  return (
    <button
      style={{ ...styles.chip, ...(active ? styles.chipActive : {}) }}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

const styles = {
  bar: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: "16px 24px 0",
  },
  search: {
    width: "100%",
    maxWidth: 420,
    padding: "9px 14px",
    fontSize: 14,
    color: "var(--text)",
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    outline: "none",
  },
  chips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  chip: {
    padding: "5px 12px",
    fontSize: 13,
    borderRadius: 999,
    background: "var(--surface)",
    border: "1px solid var(--border)",
    color: "var(--text-muted)",
  },
  chipActive: {
    background: "var(--accent)",
    borderColor: "var(--accent)",
    color: "#fff",
  },
};
