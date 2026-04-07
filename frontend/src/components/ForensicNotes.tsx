import React, { useState, useCallback } from 'react';
import { StickyNote, Plus, Send, Cpu } from 'lucide-react';
import { useTradingSystem } from '@/hooks/useTradingSystem';

export function ForensicNotes() {
  const { audit, getBaseUrl } = useTradingSystem();
  const [input, setInput] = useState('');
  const [type, setType] = useState<'OBSERVATION' | 'ALERT' | 'TRIAL'>('OBSERVATION');
  const [isSyncing, setIsSyncing] = useState(false);

  const notes = audit.notes || [];

  const addNote = async () => {
    if (!input.trim()) return;
    setIsSyncing(true);
    
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/forensic_notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: input, type })
      });
      
      if (res.ok) {
        setInput('');
      }
    } catch (e) {
      console.error('Failed to save note', e);
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="bg-[#161a25] border border-[#1e222d] rounded flex flex-col h-full overflow-hidden shadow-2xl">
      <div className="p-1.5 border-b border-[#1e222d] flex items-center justify-between bg-black/20">
        <h3 className="text-[8px] font-black uppercase tracking-widest text-blue-400 flex items-center gap-1.5">
          <StickyNote size={12} /> Notes
        </h3>
        <div className="flex items-center gap-2">
          {isSyncing && <Cpu size={10} className="animate-pulse text-blue-500" />}
          <span className="text-[7px] font-black text-slate-500 uppercase">{notes.length} ANNOTS</span>
        </div>
      </div>

      {/* Input Area */}
      <div className="p-1.5 border-b border-[#1e222d] space-y-1.5 bg-[#11141d]">
        <div className="flex items-center gap-1.5">
          {(['OBSERVATION', 'ALERT', 'TRIAL'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className={`text-[7px] font-black px-1 py-0.5 rounded transition-all border ${
                type === t 
                  ? 'bg-blue-500/20 border-blue-500/50 text-blue-400' 
                  : 'bg-slate-800/50 border-white/5 text-slate-500 hover:text-slate-400'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addNote()}
            placeholder="Add forensic observation..."
            className="flex-1 bg-black/40 border border-white/5 rounded px-2 py-1 text-[9px] text-white placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 transition-all font-mono"
          />
          <button 
            onClick={addNote}
            disabled={isSyncing}
            className="bg-blue-600 hover:bg-blue-500 text-white p-1 rounded transition-all disabled:opacity-50"
          >
            <Send size={10} />
          </button>
        </div>
      </div>

      {/* Notes List */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-2 scrollbar-hide bg-gradient-to-b from-transparent to-black/20">
        {notes.map((note: any) => (
          <div key={note.id} className="group animate-in fade-in slide-in-from-right-2 duration-300">
            <div className={`p-1.5 rounded border leading-tight text-[9px] shadow-sm ${
              note.type === 'ALERT' ? 'bg-rose-500/5 border-rose-500/20 text-rose-200' :
              note.type === 'TRIAL' ? 'bg-amber-500/5 border-amber-500/20 text-amber-200' :
              'bg-blue-500/5 border-blue-500/20 text-blue-200'
            }`}>
              <span className="font-black mr-1 text-[8px] opacity-70">[{note.type[0]}]</span>
              {note.content}
              <div className="mt-0.5 text-[7px] font-mono text-slate-500 text-right">
                {new Date(note.timestamp).toLocaleTimeString()}
              </div>
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
