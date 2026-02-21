'use client';

import { datadogRum } from '@datadog/browser-rum';
import { useEffect } from 'react';

export function DatadogInit() {
  useEffect(() => {
    // Only initialize once
    if (typeof window === 'undefined') return;
    
    try {
      datadogRum.init({
        applicationId: process.env.NEXT_PUBLIC_DATADOG_APPLICATION_ID!,
        clientToken: process.env.NEXT_PUBLIC_DATADOG_CLIENT_TOKEN!,
        site: process.env.NEXT_PUBLIC_DATADOG_SITE || 'datadoghq.com',
        service: 'continuum-web',
        env: 'hackathon',
        version: '1.0.0',
        sessionSampleRate: 100,
        sessionReplaySampleRate: 100,
        trackResources: true,
        trackLongTasks: true,
        trackUserInteractions: true,
        defaultPrivacyLevel: 'mask-user-input',
      });

      datadogRum.startSessionReplayRecording();
      
      console.log('✅ Datadog RUM initialized successfully');
    } catch (error) {
      console.error('❌ Failed to initialize Datadog RUM:', error);
    }
  }, []);

  return null;
}
