import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchBooks } from "./api";
import BookCard from "./components/BookCard";
import UploadModal from "./components/UploadModal";
import AudioPlayer from "./components/AudioPlayer";
import FilterBar from "./components/FilterBar";

const ACTIVE_STATUSES = new Set(["pending", "processing", "synthesizing"]);

export default function App() {
  const [books, setBooks] = useState([]);
  const [showUpload, setShowUpload] = useState(false);
  const [activeBook, setActiveBook] = useState(null);
  const [genre, setGenre] = useState(null);
  const [query, setQuery] = useState("");

  const visibleBooks = useMemo(() => {
    const q = query.trim().toLowerCase();
    return books.filter((b) => {
      if (genre && (b.genre || "Uncategorized") !== genre) return false;
      if (!q) return true;
      return (
        b.title.toLowerCase().includes(q) ||
        (b.author || "").toLowerCase().includes(q)
      );
    });
  }, [books, genre, query]);

  const loadBooks = useCallback(async () => {
    try {
      const data = await fetchBooks();
      setBooks(data);
      setActiveBook((prev) =>
        prev ? data.find((b) => b.id === prev.id) ?? prev : null
      );
    } catch {
      // silent — backend may not be up yet
    }
  }, []);

  useEffect(() => {
    loadBooks();
  }, [loadBooks]);

  // Poll while any book is actively processing
  useEffect(() => {
    const hasActive = books.some((b) => ACTIVE_STATUSES.has(b.status));
    if (!hasActive) return;
    const id = setInterval(loadBooks, 3000);
    return () => clearInterval(id);
  }, [books, loadBooks]);

  function handleUploaded(book) {
    setBooks((prev) => [book, ...prev]);
  }

  function handleDeleted(id) {
    setBooks((prev) => prev.filter((b) => b.id !== id));
    if (activeBook?.id === id) setActiveBook(null);
  }

  function handleUpdated(updated) {
    setBooks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
    setActiveBook((prev) => (prev?.id === updated.id ? updated : prev));
  }

  return (
    <div style={{ paddingBottom: activeBook ? 90 : 0 }}>
      <header style={styles.header}>
        <h1 style={styles.logo}>AudioBookLib</h1>
        <button style={styles.addBtn} onClick={() => setShowUpload(true)}>
          + Add Book
        </button>
      </header>

      {books.length === 0 ? (
        <div style={styles.empty}>
          <p>No books yet.</p>
          <button style={styles.addBtnLarge} onClick={() => setShowUpload(true)}>
            Upload your first PDF
          </button>
        </div>
      ) : (
        <>
          <FilterBar
            books={books}
            genre={genre}
            onGenre={setGenre}
            query={query}
            onQuery={setQuery}
          />
          {visibleBooks.length === 0 ? (
            <div style={styles.empty}>
              <p>No books match.</p>
            </div>
          ) : (
            <div style={styles.grid}>
              {visibleBooks.map((book) => (
                <BookCard
                  key={book.id}
                  book={book}
                  isPlaying={activeBook?.id === book.id}
                  onPlay={setActiveBook}
                  onDeleted={handleDeleted}
                  onUpdated={handleUpdated}
                />
              ))}
            </div>
          )}
        </>
      )}

      {showUpload && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUploaded={handleUploaded}
        />
      )}

      {activeBook && (
        <AudioPlayer book={activeBook} onClose={() => setActiveBook(null)} />
      )}
    </div>
  );
}

const styles = {
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 24px",
    borderBottom: "1px solid var(--border)",
    position: "sticky",
    top: 0,
    background: "var(--bg)",
    zIndex: 10,
  },
  logo: {
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: "-0.5px",
  },
  addBtn: {
    background: "var(--accent)",
    color: "#fff",
    borderRadius: 7,
    padding: "8px 16px",
    fontSize: 13,
    fontWeight: 500,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
    gap: 20,
    padding: 24,
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 16,
    height: "60vh",
    color: "var(--text-muted)",
  },
  addBtnLarge: {
    background: "var(--accent)",
    color: "#fff",
    borderRadius: 8,
    padding: "12px 24px",
    fontSize: 15,
    fontWeight: 500,
  },
};
