import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api/client';
export default function ConfigPanel({open,onClose}:{open:boolean; onClose:()=>void}) { const [cfg,setCfg]=useState<any>(); useEffect(()=>{ if(open) api.config().then(setCfg); },[open]); return <aside className={`config drawer ${open?'open':''}`}><div className="drawer-head"><h2>Config placeholder</h2><button onClick={onClose}><X/></button></div><p>Library path: <code>{cfg?.library_path}</code></p><p>Database path: <code>{cfg?.database_path}</code></p><ul><li>Future theme settings</li><li>Thumbnail size</li><li>Import rules</li><li>Export settings</li></ul></aside> }
