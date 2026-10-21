import Link from "next/link";

export function Nav() {
  return (
    <nav className="nav">
      <Link className="brand" href="/">
        ∎ Cogito
      </Link>
      <Link href="/documents">Documents</Link>
      <Link href="/chat">Chat</Link>
      <Link href="/dashboard">Dashboard</Link>
      <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer">
        API Docs
      </a>
    </nav>
  );
}
