import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useState, type ReactNode } from 'react';
import { categoryByKey, MAX_METRICS, METRICS, type Condition, type Priority, type World } from './data/catalog.ts';
import { INITIAL_REMOVED, SITE_SHORTLIST } from './data/placeholders/sites.ts';

export type Route = 'location' | 'category' | 'metrics' | 'sites' | 'limitations' | 'logistics' | 'risks';
export const ROUTES: Route[] = ['location', 'category', 'metrics', 'sites', 'limitations', 'logistics', 'risks'];

export interface Requirement {
  metric: string;
  condition: Condition;
  target: string;
  priority: Priority;
}

export interface Mission {
  world: World;
  category: string | null;
  requirements: Requirement[];
  removed: Record<string, string>;
  /** Chart slots. A site keeps its slot (and colour) until it leaves; empty slots are null. */
  inChart: (string | null)[];
}

type Action =
  | { type: 'world'; world: World }
  | { type: 'category'; key: string }
  | { type: 'metrics'; ids: string[] }
  | { type: 'requirement'; metric: string; patch: Partial<Requirement> }
  | { type: 'drop'; metric: string }
  | { type: 'remove-site'; id: string; reason: string }
  | { type: 'restore-site'; id: string }
  | { type: 'toggle-chart'; id: string }
  | { type: 'load'; mission: Mission };

export const MAX_IN_CHART = 5;

function requirementFor(metric: string, preset?: { condition?: Condition; priority?: Priority }): Requirement {
  return {
    metric,
    condition: preset?.condition ?? METRICS[metric]?.defaultCondition ?? 'at-least',
    target: '',
    priority: preset?.priority ?? 'medium',
  };
}

function initialInChart(removed: Record<string, string>): string[] {
  return SITE_SHORTLIST.sample.filter((s) => !(s.id in removed)).slice(0, MAX_IN_CHART).map((s) => s.id);
}

export const INITIAL: Mission = {
  world: 'moon',
  category: null,
  requirements: [],
  removed: { ...INITIAL_REMOVED },
  inChart: initialInChart(INITIAL_REMOVED),
};

function reducer(s: Mission, a: Action): Mission {
  switch (a.type) {
    case 'world':
      return { ...s, world: a.world };
    case 'category': {
      if (s.category === a.key) return s;
      const cat = categoryByKey(a.key);
      return { ...s, category: a.key, requirements: (cat?.defaults ?? []).map((d) => requirementFor(d.metric, d)) };
    }
    case 'metrics': {
      const keep = s.requirements.filter((r) => a.ids.includes(r.metric));
      const added = a.ids.filter((id) => !keep.some((r) => r.metric === id)).map((id) => requirementFor(id));
      return { ...s, requirements: [...keep, ...added].slice(0, MAX_METRICS) };
    }
    case 'requirement':
      return { ...s, requirements: s.requirements.map((r) => (r.metric === a.metric ? { ...r, ...a.patch } : r)) };
    case 'drop':
      return { ...s, requirements: s.requirements.filter((r) => r.metric !== a.metric) };
    case 'remove-site':
      return { ...s, removed: { ...s.removed, [a.id]: a.reason }, inChart: s.inChart.map((x) => (x === a.id ? null : x)) };
    case 'restore-site': {
      const { [a.id]: _gone, ...removed } = s.removed;
      return { ...s, removed };
    }
    case 'toggle-chart': {
      if (s.inChart.includes(a.id)) return { ...s, inChart: s.inChart.map((x) => (x === a.id ? null : x)) };
      if (chartIds(s).length >= MAX_IN_CHART || a.id in s.removed) return s;
      const slot = s.inChart.indexOf(null);
      const next = [...s.inChart];
      if (slot >= 0) next[slot] = a.id;
      else next.push(a.id);
      return { ...s, inChart: next };
    }
    case 'load':
      return a.mission;
  }
}

const DRAFT_KEY = 'cosmic-mission-ui:draft';

function readDraft(): Mission | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const m = JSON.parse(raw) as Mission;
    return m && (m.world === 'moon' || m.world === 'mars') && Array.isArray(m.requirements) ? m : null;
  } catch {
    return null;
  }
}

interface Ctx {
  mission: Mission;
  dispatch: (a: Action) => void;
  saveDraft: () => boolean;
}

const MissionContext = createContext<Ctx | null>(null);

export function MissionProvider({ children }: { children: ReactNode }) {
  const [mission, dispatch] = useReducer(reducer, INITIAL, (init) => readDraft() ?? init);
  const saveDraft = useCallback(() => {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(mission));
      return true;
    } catch {
      return false;
    }
  }, [mission]);
  const value = useMemo(() => ({ mission, dispatch, saveDraft }), [mission, saveDraft]);
  return <MissionContext.Provider value={value}>{children}</MissionContext.Provider>;
}

export function useMission(): Ctx {
  const ctx = useContext(MissionContext);
  if (!ctx) throw new Error('useMission outside MissionProvider');
  return ctx;
}

function parseRoute(): Route {
  const r = location.hash.replace(/^#\/?/, '') as Route;
  return ROUTES.includes(r) ? r : 'location';
}

export function useRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(parseRoute);
  useEffect(() => {
    const on = () => setRoute(parseRoute());
    addEventListener('hashchange', on);
    return () => removeEventListener('hashchange', on);
  }, []);
  const go = useCallback((r: Route) => {
    location.hash = `/${r}`;
    window.scrollTo({ top: 0 });
  }, []);
  return [route, go];
}

/** Sites still in play (not removed), in shortlist order. */
export function sitesInPlay(m: Mission) {
  return SITE_SHORTLIST.sample.filter((s) => !(s.id in m.removed));
}

export function chartIds(m: Mission): string[] {
  return m.inChart.filter((x): x is string => !!x);
}

/** Sites in the comparison chart, in slot order. */
export function sitesInChart(m: Mission) {
  return chartIds(m).map((id) => SITE_SHORTLIST.sample.find((s) => s.id === id)!).filter(Boolean);
}

export const SERIES = ['var(--chart-series-1)', 'var(--chart-series-2)', 'var(--chart-series-3)', 'var(--chart-series-4)', 'var(--chart-series-5)'];

export function seriesColor(m: Mission, siteId: string): string | null {
  const i = m.inChart.indexOf(siteId);
  return i >= 0 ? SERIES[i] : null;
}

export function isRequired(r: Requirement | undefined): boolean {
  return !!r && (r.priority === 'high' || r.priority === 'critical');
}
