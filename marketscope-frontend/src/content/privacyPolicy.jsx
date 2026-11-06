import React from 'react';
import PolicyBlank from '../components/auth/PolicyBlank';

// Bump together with PRIVACY_POLICY_VERSION in
// marketscope-backend/services/user_fields.py when this text changes.
export const PRIVACY_POLICY_VERSION = '1.0';
export const PRIVACY_POLICY_TITLE = 'Data Privacy Policy';

// Set to false once every PolicyBlank below is filled in and the text has been reviewed.
export const PRIVACY_POLICY_IS_DRAFT = true;

export const PRIVACY_POLICY_INTRO = (
  <>
    MarketScope helps local entrepreneurs in Panabo City assess business locations. This policy explains what
    personal information MarketScope collects, why, who handles it, and your rights under the Data Privacy Act of
    2012 (Republic Act No. 10173).
  </>
);

export const PRIVACY_POLICY_SECTIONS = [
  {
    
  },
  {
    heading: 'What we collect',
    body: (
      <ul>
        <li><strong>Account details:</strong> your first and last name, email address and password. Your password is stored only as a hash, not as readable text.</li>
        <li><strong>Business preferences:</strong> your primary business interest and preferred setup.</li>
        <li><strong>Details you choose to add:</strong> cellphone number, street and barangay, birthday (your age is calculated from it) and profile picture.</li>
        <li><strong>Your activity:</strong> the locations and business types you scan, their results, and any space listings you submit.</li>
        <li><strong>Your agreement:</strong> the date you accepted this policy and which version you accepted.</li>
        <li><strong>On your device:</strong> your browser keeps your session and display settings and, if you ask it to, your email address for the next login.</li>
      </ul>
    ),
  },
  {
    heading: 'Why we use it',
    body: (
      <ul>
        <li>To create and run your account.</li>
        <li>To run your location scans and save them to your history.</li>
        <li>To recommend business trends based on your preferences.</li>
        <li>To send you a code when you reset your password.</li>
      </ul>
    ),
  },
  {
    heading: 'Who else handles it',
    body: (
      <>
        <ul>
          <li><strong>MarketScope administrators</strong> can view, edit and delete accounts, and can download backups of account data.</li>
          <li><strong>Google Gemini</strong> receives scan results, such as the location, business type and scores, to write report summaries when you generate an AI report. Your name and contact details are not part of that request.</li>
          <li><strong>OpenStreetMap</strong> supplies the map images, so its servers can see your device's network address when the map loads.</li>
          <li><strong>Our email provider</strong> receives your email address and reset code to deliver password reset emails.</li>
          <li><strong>Our hosting provider:</strong> <PolicyBlank>Where MarketScope and its database are hosted</PolicyBlank></li>
        </ul>
        <p>We do not sell your personal information.</p>
      </>
    ),
  },
  {
    heading: 'How long we keep it',
    body: (
      <p>
        Your account data stays in MarketScope until the account is deleted. <PolicyBlank>How long data is kept, and when it is deleted</PolicyBlank>
      </p>
    ),
  },
  {
    heading: 'How we protect it',
    body: (
      <p>
        Passwords are stored only as hashes. <PolicyBlank>Other security measures, to be completed once account access protection is in place</PolicyBlank>
      </p>
    ),
  },
  {
    heading: 'Your rights',
    body: (
      <>
        <p>
          Under the Data Privacy Act you have the right to be informed, to access your data, to object to its
          processing, to have it corrected, to have it erased or blocked, to obtain a copy of it, and to claim
          damages. You can also file a complaint with the National Privacy Commission.
        </p>
        <p>
          You can correct most of your details yourself in Profile. To delete your account, withdraw your consent
          or use any other right, write to the contact above. Withdrawing consent may mean your account has to be closed.
        </p>
      </>
    ),
  },
  {
    heading: 'Age requirement',
    body: <p><PolicyBlank>Minimum age to register, or how parental consent is handled</PolicyBlank></p>,
  },
];
