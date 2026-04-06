import React, { useState, useEffect, useCallback } from 'react';
import { StickyNote, Plus, Send, X, Trash2, Cpu } from 'lucide-react';

export interface Note {
  id: string;
  timestamp: string;
  content: string;
  type: 'OBSERVATION' | 'ALERT' | 'TRIAL';
}

export function ForensicNotes() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [input, setInput] = useState('');
  const [type, setType] = useState<Note['type']>('OBSERVATION');
  const [isSyncing, setIsSyncing] = useState(false);

  const fetchNotes = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/api/v1/forensic_notes');
      const data = await res.json();
      setNotes(data);
    } catch (e) {
      console.error('Failed to fetch forensic notes', e);
    }
  }, []);

  useEffect(() => {
    fetchNotes();
  }, [fetchNotes]);

  const addNote = async () => {
    if (!input.trim()) return;
    setIsSyncing(true);
    
    try {
      const res = await fetch('http://localhost:8000/api/v1/forensic_notes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: input, type })
      });
      
      if (res.ok) {
        await fetchNotes();
        setInput('');
      }
    } catch (e) {
      console.error('Failed to save note', e);
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded-lg flex flex-col h-full overflow-hidden shadow-2xl">
      <div className="p-4 border-b border-[#1e222d] flex items-center justify-between bg-black/20">
        <h3 className="text-xs font-black uppercase tracking-widest text-blue-400 flex items-center gap-2">
          <StickyNote size={14} /> Forensic Notes
        </h3>
        <div className="flex items-center gap-3">
          {isSyncing && <Cpu size={12} className="animate-pulse text-blue-500" />}
          <span className="text-[10px] font-bold text-slate-500">{notes.length} ANNOTATIONS</span>
        </div>
      </div>

      {/* Input Area */}
      <div className="p-4 border-b border-[#1e222d] space-y-3 bg-[#11141d]">
        <div className="flex items-center gap-2">
          {(['OBSERVATION', 'ALERT', 'TRIAL'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className={`text-[9px] font-black px-2 py-1 rounded transition-all border ${
                type === t 
                  ? 'bg-blue-500/20 border-blue-500/50 text-blue-400' 
                  : 'bg-slate-800/50 border-white/5 text-slate-500 hover:text-slate-400'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addNote()}
            placeholder="Add forensic observation for RAG indexing..."
            className="flex-1 bg-black/40 border border-white/5 rounded px-3 py-2 text-xs text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 transition-all font-mono"
          />
          <button 
            onClick={addNote}
            disabled={isSyncing}
            className="bg-blue-600 hover:bg-blue-500 text-white p-2 rounded transition-all disabled:opacity-50"
          >
            <Send size={14} />
          </button>
        </div>
      </div>

      {/* Notes List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-hide bg-gradient-to-b from-transparent to-black/20">
        {notes.map((note) => (
          <div key={note.id} className="group animate-in fade-in slide-in-from-right-2 duration-300">
            <div className="flex items-start justify-between gap-3 mb-1">
              <span className="text-[9px] font-mono text-slate-500">
                {new Date(note.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div className={`p-3 rounded-lg border leading-relaxed text-xs shadow-sm ${
              note.type === 'ALERT' ? 'bg-rose-500/5 border-rose-500/20 text-rose-200' :
              note.type === 'TRIAL' ? 'bg-amber-500/5 border-amber-500/20 text-amber-200' :
              'bg-blue-500/5 border-blue-500/20 text-blue-200'
            }`}>
              <span className="font-black mr-2 text-[10px] opacity-70">[{note.type}]</span>
              {note.content}
            </div>
          </div>
        ))}

        {notes.length === 0 && !isSyncing && (
          <div className="h-full flex flex-col items-center justify-center text-slate-700 space-y-2 opacity-50">
            <Plus size={24} />
            <p className="text-[10px] font-black uppercase tracking-tighter">No active notes indexed for RAG</p>
          </div>
        )}
      </div>
    </div>
  );
}
