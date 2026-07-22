import { useEffect, useState, useCallback } from "react";
import {
  fetchAdminUsers,
  fetchAdminABTests,
  updateUserAccess,
  deleteABTest,
} from "../api";
import CreateABTestModal from "./CreateABTestModal";
import s from "./ABTestsAdmin.module.css";

// A little stacked bar of the three vote counts.
function ResultsBar({ results }) {
  const { A, B, no_diff, total } = results;
  if (!total) return <span className={s.noVotes}>No votes yet</span>;
  const pct = (n) => `${Math.round((n / total) * 100)}%`;
  return (
    <div className={s.results}>
      <div className={s.bar} title={`A ${A} · B ${B} · No diff ${no_diff}`}>
        <span className={s.segA} style={{ width: pct(A) }} />
        <span className={s.segB} style={{ width: pct(B) }} />
        <span className={s.segN} style={{ width: pct(no_diff) }} />
      </div>
      <span className={s.tally}>
        A {A} · B {B} · No diff {no_diff} · {total} total
      </span>
    </div>
  );
}

export default function ABTestsAdmin() {
  const [users, setUsers] = useState([]);
  const [tests, setTests] = useState([]);
  const [error, setError] = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [savingId, setSavingId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [us, ts] = await Promise.all([
        fetchAdminUsers(),
        fetchAdminABTests(),
      ]);
      setUsers(us);
      setTests(ts);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleAccess(u) {
    setSavingId(u.id);
    try {
      const updated = await updateUserAccess(u.id, !u.ab_test_access);
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingId(null);
    }
  }

  async function removeTest(t) {
    if (!window.confirm(`Delete "${t.title}" and its clips? This can't be undone.`))
      return;
    try {
      await deleteABTest(t.id);
      setTests((prev) => prev.filter((x) => x.id !== t.id));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      {error && <div className={s.error}>{error}</div>}

      <div className={s.section}>
        <h3 className={s.sectionTitle}>A/B test access</h3>
        <p className={s.hint}>
          Admins always have access. Grant a signed-in person the toggle below to
          let them see every current and future A/B test.
        </p>
        {users.length === 0 ? (
          <p className={s.empty}>No one has signed in yet.</p>
        ) : (
          <table className={s.table}>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td className={s.who}>
                    <span className={s.name}>{u.display_name || "—"}</span>
                    <span className={s.emailCell}>{u.email}</span>
                  </td>
                  <td className={s.accessCell}>
                    {u.role === "admin" ? (
                      <span className={s.badge}>admin · always</span>
                    ) : (
                      <button
                        className={`${s.toggle} ${
                          u.ab_test_access ? s.toggleOn : ""
                        }`}
                        disabled={savingId === u.id}
                        onClick={() => toggleAccess(u)}
                      >
                        {u.ab_test_access ? "Access granted" : "No access"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className={s.section}>
        <div className={s.sectionHead}>
          <h3 className={s.sectionTitle}>A/B tests</h3>
          <button className={s.newBtn} onClick={() => setShowCreate(true)}>
            + New test
          </button>
        </div>
        {tests.length === 0 ? (
          <p className={s.empty}>No tests yet.</p>
        ) : (
          <div className={s.tests}>
            {tests.map((t) => (
              <div key={t.id} className={s.testCard}>
                <div className={s.testHead}>
                  <div>
                    <span className={s.testTitle}>{t.title}</span>
                    {!t.published && (
                      <span className={s.draft}>draft</span>
                    )}
                  </div>
                  <button
                    className={s.deleteBtn}
                    onClick={() => removeTest(t)}
                  >
                    Delete
                  </button>
                </div>
                <div className={s.opts}>
                  {t.options.map((o) => (
                    <span key={o.id} className={s.opt}>
                      <b>{o.key}</b> {o.label}
                    </span>
                  ))}
                </div>
                <ResultsBar results={t.results} />
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateABTestModal
          onClose={() => setShowCreate(false)}
          onCreated={(t) => setTests((prev) => [t, ...prev])}
        />
      )}
    </>
  );
}
