import s from "./FilterBar.module.css";

export default function FilterBar({ books, genre, onGenre, query, onQuery }) {
  const counts = new Map();
  for (const b of books) {
    const g = b.genre || "Uncategorized";
    counts.set(g, (counts.get(g) || 0) + 1);
  }
  const genres = [...counts.keys()].sort();

  return (
    <div className={s.bar}>
      <input
        className={s.search}
        type="search"
        placeholder="Search title or author…"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
      <div className={s.chips}>
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
      className={`${s.chip} ${active ? s.chipActive : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
