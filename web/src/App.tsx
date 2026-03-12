import { Button } from "@/components/ui/button";

function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
      <div className="text-center space-y-4">
        <h1 className="text-3xl font-bold">Code Conductor</h1>
        <p className="text-muted-foreground">Multi-Agent Orchestration System</p>
        <Button>Get Started</Button>
      </div>
    </div>
  );
}

export default App;
