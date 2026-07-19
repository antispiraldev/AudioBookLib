import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchBooks, fetchMe, logout } from "./api";
import BookCard from "./components/BookCard";
import UploadModal from "./components/UploadModal";
import AudioPlayer from "./components/AudioPlayer";
import FilterBar from "./components/FilterBar";
import AdminPanel from "./components/AdminPanel";
import Landing from "./components/Landing";
import s from "./App.module.css";

const ACTIVE_STATUSES = new Set(["pending", "processing", "synthesizing"]);

// Minimal hash-based routing — only two views (library + admin), so a full
// router isn't worth the dependency. Returns "admin" for #/admin, else "library".
function useHashRoute() {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash === "#/admin" ? "admin" : "library";
}

export default function App() {
  const [books, setBooks] = useState([]);
  const [showUpload, setShowUpload] = useState(false);
  const [activeBook, setActiveBook] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [genre, setGenre] = useState(null);
  const [query, setQuery] = useState("");
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [loginDenied, setLoginDenied] = useState(false);
  const isAdmin = user?.role === "admin";
  const route = useHashRoute();
  // Only admins can be on the admin view; anyone else falls back to the library.
  const onAdmin = route === "admin" && isAdmin;

  useEffect(() => {
    fetchMe()
      .then(setUser)
      .catch(() => {})
      .finally(() => setAuthChecked(true));
    const params = new URLSearchParams(window.location.search);
    if (params.get("login") === "denied") {
      setLoginDenied(true);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  async function handleLogout() {
    await logout();
    setUser(null);
  }

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
    if (activeBook?.id === id) {
      setActiveBook(null);
      setPlaying(false);
    }
  }

  // Tapping a card selects + plays it; tapping the active card toggles play/pause.
  function handleCardTap(book) {
    if (activeBook?.id === book.id) {
      setPlaying((p) => !p);
    } else {
      setActiveBook(book);
      setPlaying(true);
    }
  }

  function closePlayer() {
    setActiveBook(null);
    setPlaying(false);
  }

  function handleUpdated(updated) {
    setBooks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
    setActiveBook((prev) => (prev?.id === updated.id ? updated : prev));
  }

  // Wait for the auth check before rendering anything, so a signed-in user
  // doesn't get a flash of the landing page on every refresh.
  if (!authChecked) return null;

  // Logged-out visitors get the landing page instead of the app shell. Note this
  // is a visual gate only — see Landing.jsx.
  if (!user) {
    return (
      <Landing denied={loginDenied} onDismissDenied={() => setLoginDenied(false)} />
    );
  }

  return (
    <div style={{ paddingBottom: activeBook && !onAdmin ? 90 : 0 }}>
      <header className={s.header}>
        <h1 className={s.logo}>Aedo</h1>
        <div className={s.right}>
          {isAdmin && (
            <a className={s.navLink} href={onAdmin ? "#/" : "#/admin"}>
              {onAdmin ? "Library" : "Admin"}
            </a>
          )}
          {isAdmin && !onAdmin && (
            <button className={s.addBtn} onClick={() => setShowUpload(true)}>
              +<span className={s.addLabel}> Add Book</span>
            </button>
          )}
          {/* Only signed-in users reach this render; logged-out visitors get
              the landing page, which owns the sign-in button. */}
          <span className={s.userName}>{user.display_name || user.email}</span>
          <button className={s.authBtn} onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>

      {onAdmin ? (
        <AdminPanel />
      ) : books.length === 0 ? (
        <div className={s.empty}>
          <p>No books yet.</p>
          {isAdmin && (
            <button className={s.addBtnLarge} onClick={() => setShowUpload(true)}>
              Upload your first PDF
            </button>
          )}
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
            <div className={s.empty}>
              <p>No books match.</p>
            </div>
          ) : (
            <div className={s.grid}>
              {visibleBooks.map((book) => (
                <BookCard
                  key={book.id}
                  book={book}
                  isAdmin={isAdmin}
                  isActive={activeBook?.id === book.id}
                  playing={playing}
                  onPlay={handleCardTap}
                  onDeleted={handleDeleted}
                  onUpdated={handleUpdated}
                />
              ))}
            </div>
          )}
        </>
      )}

      {showUpload && !onAdmin && (
        <UploadModal
          onClose={() => setShowUpload(false)}
          onUploaded={handleUploaded}
        />
      )}

      {activeBook && !onAdmin && (
        <AudioPlayer
          book={activeBook}
          playing={playing}
          setPlaying={setPlaying}
          onClose={closePlayer}
        />
      )}
    </div>
  );
}
