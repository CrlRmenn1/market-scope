import React from 'react';

// Desktop panel drawing: a pin dropped on streets with its scan ring drawing out
// once, the product's core action. Illustrative only, not a real map of Panabo.
// The resting state is the finished drawing, so reduced motion simply skips the
// animation (see the .auth-art rules in auth.css).
const MINOR_STREETS = [
  'M120 250 L380 410', 'M60 400 L340 545', 'M210 170 L470 330', 'M360 120 L590 270',
  'M520 60 L740 190', 'M640 180 L470 470', 'M740 260 L560 560', 'M250 300 L120 520',
  'M400 210 L230 480', 'M90 700 L360 610', 'M140 840 L420 720', 'M520 570 L780 640',
  'M500 680 L800 790', 'M560 400 L800 470', 'M300 620 L250 860', 'M600 620 L560 900',
];

const NEARBY_BUSINESSES = [
  [445, 322], [566, 345], [530, 462], [402, 410], [612, 415],
];

export default function ScanMapArt() {
  return (
    <svg className="auth-art" viewBox="0 0 800 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <path className="auth-art-river" d="M830 730 C680 700 610 790 520 810 S300 880 230 1030" />
      <g className="auth-art-streets">
        {MINOR_STREETS.map((street) => <path key={street} d={street} />)}
      </g>
      <g className="auth-art-roads">
        <path d="M-20 650 C140 610 270 570 420 480 S700 300 830 250" />
        <path d="M300 -20 C320 160 380 320 420 480 S480 800 450 1030" />
      </g>
      <circle className="auth-art-ring-fill" cx="500" cy="385" r="165" />
      <circle className="auth-art-ring" cx="500" cy="385" r="165" pathLength="1" transform="rotate(-90 500 385)" />
      <g className="auth-art-dots">
        {NEARBY_BUSINESSES.map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="6" />)}
      </g>
      <g className="auth-art-pin">
        <path d="M500 385 C500 385 470 345 470 323 A30 30 0 1 1 530 323 C530 345 500 385 500 385 Z" />
        <circle cx="500" cy="323" r="11" />
      </g>
    </svg>
  );
}
