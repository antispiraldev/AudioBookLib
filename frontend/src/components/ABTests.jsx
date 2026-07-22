import { useEffect, useState, useCallback } from "react";
import { fetchABTests, voteABTest } from "../api";
import s from "./ABTests.module.css";

const CHOICE_LABEL = { A: "A", B: "B", no_diff: "No difference" };

export default function ABTests() {
  const [tests, setTests] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // test id currently saving a vote

  const load = useCallback(async () => {
    try {
      setTests(await fetchABTests());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleVote(testId, choice) {
    setBusy(testId);
    const prev = tests;
    // Optimistic — reveal labels and highlight immediately.
    setTests((ts) =>
      ts.map((t) => (t.id === testId ? { ...t, my_vote: choice } : t))
    );
    try {
      await voteABTest(testId, choice);
    } catch (e) {
      setTests(prev); // roll back
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <div className={s.state}>Loading…</div>;
  if (error) return <div className={s.stateError}>Couldn't load: {error}</div>;
  if (tests.length === 0)
    return (
      <div className={s.state}>
        No A/B tests yet. New listening comparisons will show up here.
      </div>
    );

  return (
    <div className={s.wrap}>
      <div className={s.intro}>
        <h2 className={s.pageTitle}>A/B tests</h2>
        <p className={s.pageSub}>
          Listen to both clips and pick the one you prefer. Which is which is
          hidden until you vote, so trust your ears.
        </p>
      </div>

      {tests.map((test) => {
        const voted = test.my_vote != null;
        return (
          <div key={test.id} className={s.card}>
            <h3 className={s.title}>{test.title}</h3>
            {test.description && <p className={s.desc}>{test.description}</p>}

            <div className={s.options}>
              {test.options.map((o) => {
                const picked = test.my_vote === o.key;
                return (
                  <div
                    key={o.id}
                    className={`${s.option} ${picked ? s.optionPicked : ""}`}
                  >
                    <div className={s.optHead}>
                      <span className={s.optKey}>{o.key}</span>
                      {voted && <span className={s.optLabel}>{o.label}</span>}
                    </div>
                    {o.audio_url ? (
                      <audio
                        className={s.audio}
                        controls
                        preload="none"
                        src={o.audio_url}
                      />
                    ) : (
                      <span className={s.noClip}>Clip unavailable</span>
                    )}
                    <button
                      className={`${s.voteBtn} ${picked ? s.voteBtnActive : ""}`}
                      disabled={busy === test.id}
                      onClick={() => handleVote(test.id, o.key)}
                    >
                      {picked ? "Your pick" : `Prefer ${o.key}`}
                    </button>
                  </div>
                );
              })}
            </div>

            <div className={s.footer}>
              <button
                className={`${s.noDiff} ${
                  test.my_vote === "no_diff" ? s.noDiffActive : ""
                }`}
                disabled={busy === test.id}
                onClick={() => handleVote(test.id, "no_diff")}
              >
                No difference
              </button>
              {voted && (
                <span className={s.voted}>
                  You picked <strong>{CHOICE_LABEL[test.my_vote]}</strong> — tap
                  to change
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
