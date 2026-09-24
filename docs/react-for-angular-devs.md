# React for Angular developers — just enough to defend this frontend

You know TypeScript, components, routing, services and RxJS. React covers the same ground with fewer concepts: **components are functions, state lives in hooks, and data flows down through props.**

## Concept map

| Angular | React (in this project) | Note |
|---|---|---|
| `@Component` class + template | Function returning JSX | JSX is TypeScript with HTML-like syntax; `className` instead of `class` |
| `@Input()` | Props (function parameters) | `function EpisodeCard({ episode }: { episode: Episode })` |
| `@Output()` + `EventEmitter` | Callback props | `onPlay={() => ...}` |
| Component fields + change detection | `useState` | Setting state re-renders the component; no zones |
| `ngOnInit` / `ngOnDestroy` | `useEffect(() => { ...; return cleanup }, [deps])` | Runs after render when `deps` change |
| `*ngIf` / `*ngFor` | `{cond && <X/>}` / `{items.map(i => <X key={i.id}/>)}` | Plain JS expressions; `key` is required in lists |
| Services + DI | Plain modules (`api/client.ts`) and custom hooks (`useEpisodes()`) | No DI container |
| `HttpClient` + RxJS | `fetch` wrapped by **TanStack Query** (`useQuery`, `useMutation`) | Caching, loading/error states, refetch, polling |
| `RouterModule` | **React Router** (`<Routes>`, `<Route>`, `useNavigate`) | Route guards = a wrapper component that redirects |
| Reactive forms | Controlled inputs with `useState` | Small forms here; no form library needed |
| Global store (NgRx) | Not used | Server state lives in TanStack Query; auth token in a small context |

## The patterns you'll see in this repo

```tsx
// Data fetching with polling while an episode is generating
function EpisodeStatus({ id }: { id: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["episode", id],
    queryFn: () => api.getEpisode(id),
    refetchInterval: (q) => (q.state.data?.status === "ready" ? false : 3000),
  });
  if (isLoading) return <Spinner />;
  return <span>{data!.status}</span>;
}

// Mutation + cache invalidation (like calling a service then refreshing a list)
const generate = useMutation({
  mutationFn: (focus: string) => api.generateEpisode(focus),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["episodes"] }),
});

// Admin-only route (a "guard")
function RequireAdmin({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  return user?.is_admin ? children : <Navigate to="/" replace />;
}
```

## Questions you might get, and short answers
- **Why TanStack Query instead of a store?** Almost all state here is server state (episodes, preferences, metrics). The query cache handles loading, errors, polling and invalidation; a store would duplicate it.
- **How does the episode status update live?** `refetchInterval` polls every 3 s while status isn't `ready`/`failed`. SSE or WebSockets are the upgrade path; polling is simpler and enough at this scale.
- **Why Vite?** Fast dev server and build, the current default for new React apps.
- **Where is auth stored?** JWT in memory plus `localStorage` for refresh on reload; production would use httpOnly cookies.
