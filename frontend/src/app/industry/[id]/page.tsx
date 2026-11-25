"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { MacroPanel } from "@/components/MacroPanel";
import { NewsList } from "@/components/NewsList";
import { PeersTable } from "@/components/PeersTable";
import { ErrorBox, Loading, Section } from "@/components/ui";
import { getJSON } from "@/lib/api";
import type { IndustryPage } from "@/lib/types";

export default function IndustryView() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<IndustryPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJSON<IndustryPage>(`/api/industry/${id}`).then(setD).catch((e) => setError(`Could not load this industry (${e.message}).`));
  }, [id]);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!d) return <Loading what="industry" />;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">{d.label}</h1>
      <MacroPanel macro={d.macro} title="Economy check" />
      <Section title="Companies in this industry" subtitle={`Top ${d.peers.length} of ${d.total_members} by value traded. ${d.membership_note}`}>
        <PeersTable peers={d.peers} />
      </Section>
      <NewsList news={d.news} title="Industry news" />
    </div>
  );
}
