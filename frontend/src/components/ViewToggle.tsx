import type { ViewMode } from '../types';
import type { Translator } from '../utils/i18n';
export default function ViewToggle({view,onView,t}:{view:ViewMode; onView:(v:ViewMode)=>void; t: Translator}) { return <div className="toggle"><button className={view==='explore'?'active':''} onClick={()=>onView('explore')}>{t('explore')}</button><button className={view==='cards'?'active':''} onClick={()=>onView('cards')}>{t('cards')}</button></div> }
