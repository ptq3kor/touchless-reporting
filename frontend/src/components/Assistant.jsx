import { useState } from 'react';
import { streamSSE } from '../api.js';

export default function Assistant({ filters }) {
  const [open, setOpen] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    setNotice(null);
    const history = [...messages, { role: 'user', content: text }];
    setMessages([...history, { role: 'assistant', content: '' }]);
    setBusy(true);
    try {
      await streamSSE('/api/assistant/chat', { messages: history, filters }, {
        onDelta: (d) =>
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = {
              role: 'assistant',
              content: next[next.length - 1].content + d,
            };
            return next;
          }),
        onError: (e) => {
          setNotice(e);
          setMessages(history);
        },
        onDone: () => setBusy(false),
      });
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="assistant">
      <button className="assistant-toggle" onClick={() => setOpen((o) => !o)}>
        AI Assistant {open ? '▾' : '▸'}
      </button>
      {open && (
        <div className="assistant-body">
          <div className="assistant-messages">
            {messages.length === 0 && !notice && (
              <p className="muted small">Ask about the numbers — e.g. “Why did TNS grow vs PY?”</p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`msg msg-${m.role}`}>{m.content || '…'}</div>
            ))}
            {notice && <p className="notice">{notice}</p>}
          </div>
          <div className="assistant-input">
            <input
              value={input}
              placeholder="Ask about the numbers…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send()}
              disabled={busy}
            />
            <button className="btn-primary" onClick={send} disabled={busy || !input.trim()}>
              Send
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
