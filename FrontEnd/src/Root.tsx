import { lazy, Suspense } from "react";
import { Brand } from "./components/Shared";
const App = lazy(() => import("./App"));
const LandingPage = lazy(() => import("./features/LandingPage"));
export default function Root() {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  return (
    <Suspense
      fallback={
        <div className="route-loading" role="status">
          <Brand />
          <p>Chargement…</p>
        </div>
      }
    >
      {path === "/" ? (
        <LandingPage />
      ) : path === "/app" ? (
        <App />
      ) : (
        <div className="route-loading">
          <Brand />
          <h1>Cette page n’existe pas.</h1>
          <a className="button primary" href="/">
            Retour à l’accueil
          </a>
        </div>
      )}
    </Suspense>
  );
}
