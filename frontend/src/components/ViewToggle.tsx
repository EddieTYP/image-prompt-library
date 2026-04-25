import type { ViewMode } from '../types';
export default function ViewToggle({view,onView}:{view:ViewMode; onView:(v:ViewMode)=>void}) { return <div className="toggle"><button className={view==='explore'?'active':''} onClick={()=>onView('explore')}>Explore</button><button className={view==='cards'?'active':''} onClick={()=>onView('cards')}>Cards</button></div> }
