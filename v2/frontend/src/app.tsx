import {Suspense} from 'react';
import {useSuspenseQuery} from '@tanstack/react-query';
import {Navigate, Route, Routes, useParams} from 'react-router-dom';

import {conversationLaneQuery, type ConversationSpace} from './api/queries';

function ConversationLanePage() {
  const {space: rawSpace} = useParams();
  const space: ConversationSpace = rawSpace === 'demo' ? 'demo' : 'real';
  const {data} = useSuspenseQuery(conversationLaneQuery(space));

  return (
    <main>
      <h1>{space === 'demo' ? 'Demo conversations' : 'Consultations'}</h1>
      {Object.values(data.groups).every((group) => group.length === 0) ? (
        <p>No conversations are available.</p>
      ) : (
        Object.entries(data.groups).map(([name, conversations]) => (
          conversations.length > 0 && (
            <section key={name} aria-labelledby={`group-${name}`}>
              <h2 id={`group-${name}`}>{name.replace(/([A-Z])/g, ' $1')}</h2>
              <ul>
                {conversations.map((conversation) => (
                  <li key={`${name}-${conversation.slug}`}>
                    <a href={conversation.links.self}>{conversation.title}</a>
                  </li>
                ))}
              </ul>
            </section>
          )
        ))
      )}
    </main>
  );
}

export function App() {
  return (
    <Suspense fallback={<p role="status">Loading conversations…</p>}>
      <Routes>
        <Route path="/app/:space" element={<ConversationLanePage />} />
        <Route path="*" element={<Navigate to="/app/real" replace />} />
      </Routes>
    </Suspense>
  );
}
