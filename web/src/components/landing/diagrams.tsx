import type { CSSProperties } from "react";

/* Diagrams for the landing page. Pure SVG, coloured by theme tokens (see .dg in globals.css). */

export function QualityDropChart() {
  // days 0-30 -> x 60-860; quality 0-100% -> y 240-40. Illustrative data, labelled as such by the caption.
  return (
    <svg className="dg block h-auto w-full" viewBox="0 0 880 290" role="img"
      aria-label="Line chart. A chatbot's answer quality stays near 93 percent for ten days, falls to about 60 percent when its documents are updated, and users only complain on day 24. EvalGuard would have alerted on day 11.">
      <rect className="shade appear-late" x="353" y="40" width="347" height="200" />
      <g>
        <line className="grid" x1="60" y1="40" x2="860" y2="40" /><line className="grid" x1="60" y1="90" x2="860" y2="90" />
        <line className="grid" x1="60" y1="140" x2="860" y2="140" /><line className="grid" x1="60" y1="190" x2="860" y2="190" />
      </g>
      <line className="ln" x1="60" y1="240" x2="860" y2="240" /><line className="ln" x1="60" y1="40" x2="60" y2="240" />
      <g className="m s" textAnchor="end">
        <text className="m s" x="52" y="44">100%</text><text className="m s" x="52" y="94">75%</text>
        <text className="m s" x="52" y="144">50%</text><text className="m s" x="52" y="194">25%</text>
      </g>
      <g textAnchor="middle">
        <text className="m s" x="60" y="260">day 0</text><text className="m s" x="327" y="260">day 10</text>
        <text className="m s" x="593" y="260">day 20</text><text className="m s" x="860" y="260">day 30</text>
      </g>
      <polyline className="line-ok draw" pathLength={1}
        points="60,54 113,52 167,56 220,54 273,52 327,54 348,112 380,118 433,114 487,120 540,116 593,122 647,118 700,120 753,124 807,120 860,122" />
      <line className="line-bad" x1="327" y1="34" x2="327" y2="240" />
      <line className="line-bad" x1="353" y1="34" x2="353" y2="240" />
      <line className="line-bad appear-late" x1="700" y1="34" x2="700" y2="240" />
      <circle className="pulse-ring" cx="353" cy="112" r="7" />
      <circle className="dot-ok" cx="353" cy="112" r="4.5" />
      <text className="b s" x="321" y="22" textAnchor="end">Documents updated</text>
      <text className="ok s" x="359" y="22">EvalGuard alert (day 11)</text>
      <text className="bad s appear-late" x="700" y="22" textAnchor="middle">Users complain (day 24)</text>
      <text className="bad appear-late" x="526" y="180" textAnchor="middle">13 days of wrong answers</text>
      <text className="bad appear-late" x="526" y="199" textAnchor="middle">going out unnoticed</text>
      <text className="m s" x="190" y="86" textAnchor="middle">still fine</text>
      <text className="m s" x="780" y="106" textAnchor="middle">quality stays low</text>
    </svg>
  );
}

export function FlowDiagram() {
  return (
    <svg className="dg block h-auto w-full" viewBox="0 0 880 410" role="img"
      aria-label="Six-step flow. Top row, the chatbot being tested: a question is asked, the documents are searched, the chatbot writes an answer. Bottom row, the checker: a judge AI reads the answer, produces scores, and the result is saved and compared with the last good run, with an alert if quality dropped.">
      <defs>
        <marker id="fl-ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="currentColor" /></marker>
      </defs>
      <rect className="lane" x="8" y="34" width="864" height="140" rx="14" />
      <rect className="lane" x="8" y="214" width="864" height="186" rx="14" />
      <text className="b" x="24" y="56">The chatbot being tested</text>
      <text className="b" x="24" y="236">The checker, a different AI</text>

      <rect className="step box-acc" style={{ "--at": "-0.4s" } as CSSProperties} x="20" y="84" width="190" height="72" rx="12" />
      <circle className="num" cx="38" cy="102" r="11" /><text className="num-t" x="38" y="106">1</text>
      <text className="b" x="56" y="107">Question</text><text className="m s" x="34" y="132">taken from the test list</text>
      <line className="ln" x1="210" y1="120" x2="343" y2="120" markerEnd="url(#fl-ah)" /><text className="m s" x="277" y="112" textAnchor="middle">looks up</text>

      <rect className="step box-acc" style={{ "--at": "1.77s" } as CSSProperties} x="345" y="84" width="190" height="72" rx="12" />
      <circle className="num" cx="363" cy="102" r="11" /><text className="num-t" x="363" y="106">2</text>
      <text className="b" x="381" y="107">Search</text><text className="m s" x="359" y="132">finds the right pieces</text>
      <line className="ln" x1="535" y1="120" x2="668" y2="120" markerEnd="url(#fl-ah)" /><text className="m s" x="602" y="112" textAnchor="middle">hands over</text>

      <rect className="step box-acc" style={{ "--at": "3.93s" } as CSSProperties} x="670" y="84" width="190" height="72" rx="12" />
      <circle className="num" cx="688" cy="102" r="11" /><text className="num-t" x="688" y="106">3</text>
      <text className="b" x="706" y="107">Answer</text><text className="m s" x="684" y="132">chatbot writes a reply</text>

      <line className="ln" x1="765" y1="156" x2="765" y2="282" markerEnd="url(#fl-ah)" />
      <text className="m s" x="753" y="205" textAnchor="end">the answer, the pieces used,</text>
      <text className="m s" x="753" y="222" textAnchor="end">and the known right answer</text>

      <rect className="step box" style={{ "--at": "5.27s" } as CSSProperties} x="670" y="284" width="190" height="72" rx="12" />
      <circle className="num" cx="688" cy="302" r="11" /><text className="num-t" x="688" y="306">4</text>
      <text className="b" x="706" y="307">Judge</text><text className="m s" x="684" y="332">a second AI marks it</text>
      <line className="ln" x1="670" y1="320" x2="537" y2="320" markerEnd="url(#fl-ah)" /><text className="m s" x="603" y="312" textAnchor="middle">gives marks</text>

      <rect className="step box" style={{ "--at": "7.43s" } as CSSProperties} x="345" y="284" width="190" height="72" rx="12" />
      <circle className="num" cx="363" cy="302" r="11" /><text className="num-t" x="363" y="306">5</text>
      <text className="b" x="381" y="307">Scores</text><text className="m s" x="359" y="332">honesty, correctness, more</text>
      <line className="ln" x1="345" y1="320" x2="212" y2="320" markerEnd="url(#fl-ah)" /><text className="m s" x="278" y="312" textAnchor="middle">filed away</text>

      <rect className="step box-ok" style={{ "--at": "9.6s" } as CSSProperties} x="20" y="284" width="190" height="72" rx="12" />
      <circle className="num" cx="38" cy="302" r="11" /><text className="num-t" x="38" y="306">6</text>
      <text className="b" x="56" y="307">Compare</text><text className="m s" x="34" y="332">with the last good run</text>
      <line className="ln" x1="115" y1="356" x2="115" y2="372" />
      <rect className="box-bad" x="20" y="368" width="190" height="26" rx="13" />
      <text className="bad s" x="115" y="385" textAnchor="middle">alert if quality dropped</text>
      <circle className="packet" r="6">
        <animateMotion dur="10s" repeatCount="indefinite" path="M115,120 L440,120 L765,120 L765,320 L440,320 L115,320" />
      </circle>
    </svg>
  );
}

export function DriftDots() {
  // score 0-100% -> x = 60 + 7.8 * score
  return (
    <svg className="dg block h-auto w-full" viewBox="0 0 880 250" role="img"
      aria-label="Two rows of dots on a 0 to 100 percent scale. Last week's scores cluster between 84 and 97 percent. This week's scores are spread between 28 and 70 percent. An arrow marks the gap between the two groups.">
      <defs>
        <marker id="dr-ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="currentColor" /></marker>
      </defs>
      <text className="b" x="60" y="26">Last week (the baseline)</text>
      <g className="dot-ok bob">
        <circle cx="715" cy="58" r="7" style={{ "--i": 0 } as CSSProperties} />
        <circle cx="746" cy="50" r="7" style={{ "--i": 1 } as CSSProperties} />
        <circle cx="762" cy="64" r="7" style={{ "--i": 2 } as CSSProperties} />
        <circle cx="770" cy="50" r="7" style={{ "--i": 3 } as CSSProperties} />
        <circle cx="785" cy="62" r="7" style={{ "--i": 4 } as CSSProperties} />
        <circle cx="793" cy="48" r="7" style={{ "--i": 5 } as CSSProperties} />
        <circle cx="801" cy="64" r="7" style={{ "--i": 6 } as CSSProperties} />
        <circle cx="809" cy="52" r="7" style={{ "--i": 7 } as CSSProperties} />
        <circle cx="816" cy="66" r="7" style={{ "--i": 8 } as CSSProperties} />
        <circle cx="754" cy="66" r="7" style={{ "--i": 9 } as CSSProperties} />
        <circle cx="731" cy="48" r="7" style={{ "--i": 10 } as CSSProperties} />
        <circle cx="780" cy="40" r="7" style={{ "--i": 11 } as CSSProperties} />
      </g>
      <line className="ln" x1="770" y1="96" x2="448" y2="96" markerStart="url(#dr-ah)" markerEnd="url(#dr-ah)" />
      <text className="b" x="609" y="88" textAnchor="middle">the gap</text>
      <text className="m s" x="609" y="116" textAnchor="middle">is it bigger than chance?</text>
      <text className="b" x="60" y="140">This week</text>
      <g className="dot-bad bob">
        <circle cx="279" cy="172" r="7" style={{ "--i": 0 } as CSSProperties} />
        <circle cx="333" cy="164" r="7" style={{ "--i": 1 } as CSSProperties} />
        <circle cx="380" cy="176" r="7" style={{ "--i": 2 } as CSSProperties} />
        <circle cx="427" cy="162" r="7" style={{ "--i": 3 } as CSSProperties} />
        <circle cx="466" cy="174" r="7" style={{ "--i": 4 } as CSSProperties} />
        <circle cx="490" cy="160" r="7" style={{ "--i": 5 } as CSSProperties} />
        <circle cx="512" cy="178" r="7" style={{ "--i": 6 } as CSSProperties} />
        <circle cx="544" cy="164" r="7" style={{ "--i": 7 } as CSSProperties} />
        <circle cx="575" cy="176" r="7" style={{ "--i": 8 } as CSSProperties} />
        <circle cx="404" cy="182" r="7" style={{ "--i": 9 } as CSSProperties} />
        <circle cx="356" cy="160" r="7" style={{ "--i": 10 } as CSSProperties} />
        <circle cx="606" cy="168" r="7" style={{ "--i": 11 } as CSSProperties} />
      </g>
      <line className="ln" x1="60" y1="204" x2="840" y2="204" />
      <g textAnchor="middle">
        <text className="m s" x="60" y="228">0%</text><text className="m s" x="255" y="228">25%</text><text className="m s" x="450" y="228">50%</text>
        <text className="m s" x="645" y="228">75%</text><text className="m s" x="840" y="228">100%</text>
      </g>
    </svg>
  );
}

export function ChangesDiagram() {
  const rows = [
    { y: 20, a: ["The documents change", "a new policy file is uploaded"], b: ["Run the questions again", "same questions, new documents"], c: ["Drift check", "flags a drop in the scores"] },
    { y: 115, a: ["A new AI model", "the provider swaps the model"], b: ["Compare models", "Experiments, same questions"], c: ["Side-by-side table", "which model answers best"] },
    { y: 210, a: ["The prompt is edited", "someone tweaks the wording"], b: ["Compare prompts", "Experiments, same questions"], c: ["Side-by-side table", "which wording wins"] },
  ];
  return (
    <svg className="dg block h-auto w-full" viewBox="0 0 880 300" role="img"
      aria-label="Three rows, each with three steps. Documents change leads to run again, which leads to a drift check. A new AI model leads to compare models, which leads to a side-by-side table. A prompt edit leads to compare prompts, which leads to a side-by-side table.">
      <defs>
        <marker id="ch-ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="currentColor" /></marker>
      </defs>
      {rows.map((r) => (
        <g key={r.y}>
          <rect className="box-bad" x="20" y={r.y} width="230" height="70" rx="12" /><text className="b" x="36" y={r.y + 29}>{r.a[0]}</text><text className="m s" x="36" y={r.y + 52}>{r.a[1]}</text>
          <line className="ln" x1="250" y1={r.y + 35} x2="323" y2={r.y + 35} markerEnd="url(#ch-ah)" />
          <rect className="box-acc" x="325" y={r.y} width="230" height="70" rx="12" /><text className="b" x="341" y={r.y + 29}>{r.b[0]}</text><text className="m s" x="341" y={r.y + 52}>{r.b[1]}</text>
          <line className="ln" x1="555" y1={r.y + 35} x2="628" y2={r.y + 35} markerEnd="url(#ch-ah)" />
          <rect className="box-ok" x="630" y={r.y} width="230" height="70" rx="12" /><text className="b" x="646" y={r.y + 29}>{r.c[0]}</text><text className="m s" x="646" y={r.y + 52}>{r.c[1]}</text>
        </g>
      ))}
    </svg>
  );
}
