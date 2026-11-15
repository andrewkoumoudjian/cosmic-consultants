import { AnimatePresence, motion, MotionConfig } from 'motion/react';
import { useEffect, useState } from 'react';
import { categoryByKey, WORLDS } from './data/catalog.ts';
import { Button, Modal } from './components/ui.tsx';
import { Header, Sidebar } from './components/shell.tsx';
import { CategoryStep, LocationStep, MetricsStep, targetIsSet } from './screens/Setup.tsx';
import { SiteFinder } from './screens/SiteFinder.tsx';
import { Limitations } from './screens/Limitations.tsx';
import { Logistics } from './screens/Logistics.tsx';
import { Risks } from './screens/Risks.tsx';
import { useMission, useRoute, type Route } from './state.tsx';

const REPORT_CRUMB: Partial<Record<Route, string>> = {
  sites: 'Site finder',
  limitations: 'Limitation report',
  logistics: 'Logistics',
  risks: 'Risks',
};

export function App() {
  const { mission, saveDraft } = useMission();
  const [route, go] = useRoute();
  const [saved, setSaved] = useState<null | boolean>(null);
  const [highlight, setHighlight] = useState(false);

  const cat = categoryByKey(mission.category);
  const missionReady = !!cat && mission.requirements.length > 0 && mission.requirements.every(targetIsSet);
  const isReport = route in REPORT_CRUMB;

  // Reports need a defined mission; send people back to the step that's missing.
  useEffect(() => {
    if (isReport && !missionReady) go(cat ? 'metrics' : 'category');
  }, [isReport, missionReady, cat, go]);

  useEffect(() => {
    document.title = `${isReport ? REPORT_CRUMB[route] : 'Define mission'} · cosmic / consultants`;
  }, [route, isReport]);

  const crumbs = isReport ? `Missions / ${WORLDS[mission.world].label} / ${cat?.name ?? ''} / ${REPORT_CRUMB[route]}` : 'Missions / Define mission';
  const action = isReport ? (
    <Button variant="secondary" onClick={() => window.print()}>
      Export report
    </Button>
  ) : (
    <Button variant="secondary" onClick={() => setSaved(saveDraft())}>
      Save draft
    </Button>
  );

  const screen = (() => {
    switch (route) {
      case 'location': return <LocationStep go={go} />;
      case 'category': return <CategoryStep go={go} />;
      case 'metrics': return <MetricsStep go={go} />;
      case 'sites': return missionReady ? <SiteFinder go={go} /> : null;
      case 'limitations': return missionReady ? <Limitations go={go} /> : null;
      case 'logistics': return missionReady ? <Logistics go={go} /> : null;
      case 'risks': return missionReady ? <Risks go={go} /> : null;
    }
  })();

  return (
    <MotionConfig reducedMotion="user">
      <div className={`app${highlight ? ' show-pending' : ''}`}>
        <Sidebar route={route} highlight={highlight} onHighlight={setHighlight} />
        <main className="main">
          <Header crumbs={crumbs} action={action} />
          <AnimatePresence mode="wait">
            <motion.div
              key={route}
              className="screen"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
            >
              {screen}
            </motion.div>
          </AnimatePresence>
        </main>
        <Modal open={saved !== null} onClose={() => setSaved(null)} label="Draft saved" width={400}>
          <div className="toast">
            <p className="t-section">{saved ? 'Draft saved' : 'Draft not saved'}</p>
            {!saved && <p className="t-small t-muted">This browser blocked local storage.</p>}
            <Button variant="ghost" onClick={() => setSaved(null)}>
              Close
            </Button>
          </div>
        </Modal>
      </div>
    </MotionConfig>
  );
}
