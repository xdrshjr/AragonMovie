'use client';

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Header from '@/components/Header';
import StepContainer from '@/components/StepContainer';
import ModeSidebar from '@/components/ModeSidebar';
import Step0VideoTypeSelection from '@/components/steps/Step0VideoTypeSelection';
import Step1ScriptInput from '@/components/steps/Step1ScriptInput';
import Step2CharacterImages from '@/components/steps/Step2CharacterImages';
import Step3SceneImages from '@/components/steps/Step3SceneImages';
import Step4VideoProgress from '@/components/steps/Step4VideoProgress';
import Step5ResultPreview from '@/components/steps/Step5ResultPreview';
import QuickStep1ImageUpload from '@/components/steps/QuickStep1ImageUpload';
import QuickStep2SceneConfig from '@/components/steps/QuickStep2SceneConfig';
import { Character, Scene, GenerationMode, QuickModeScene } from '@/lib/types';
import { VideoType, VideoSubtype } from '@/lib/types/videoTypes';
import { logger } from '@/lib/logger';

interface VideoContinuityConfig {
  enableSceneContinuity: boolean;
  continuityFrameIndex: number;
  continuityReferenceWeight: number;
  enableSmartContinuityJudge: boolean;
}

export default function WorkflowPage() {
  const searchParams = useSearchParams();

  // Get initial values from URL params
  const urlVideoType = searchParams.get('videoType') as VideoType | null;
  const urlMode = searchParams.get('mode') as GenerationMode | null;

  // Mode state
  const [generationMode, setGenerationMode] = useState<GenerationMode>(urlMode || 'full');

  // Full mode state
  const [currentStep, setCurrentStep] = useState(0);
  const [videoType, setVideoType] = useState<VideoType | null>(urlVideoType);
  const [videoSubtype, setVideoSubtype] = useState<VideoSubtype | null>(null);
  const [continuityConfig, setContinuityConfig] = useState<VideoContinuityConfig>({
    enableSceneContinuity: true,
    continuityFrameIndex: -5,
    continuityReferenceWeight: 0.5,
    enableSmartContinuityJudge: true,
  });
  const [userScript, setUserScript] = useState('');
  const [polishedScript, setPolishedScript] = useState('');
  const [characters, setCharacters] = useState<Character[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);

  // Quick mode state
  const [quickStep, setQuickStep] = useState(1);
  const [quickScenes, setQuickScenes] = useState<QuickModeScene[]>([]);

  // Shared state
  const [videoUrl, setVideoUrl] = useState('');
  const [videoMetadata, setVideoMetadata] = useState<any>(null);

    // Handle mode change
  const handleModeChange = (newMode: GenerationMode) => {
    if (newMode === generationMode) return;

    // Confirm if user has unsaved work
    const hasWork = generationMode === 'full'
      ? (userScript || polishedScript || characters.length > 0)
      : (quickScenes.length > 0);

    if (hasWork) {
      const confirmed = window.confirm(
        '切换模式将清空当前进度，确定要继续吗？'
      );
      if (!confirmed) return;
    }

    logger.info('MainApp', `Switching mode: ${generationMode} -> ${newMode}`);

    // Reset state
    setGenerationMode(newMode);
    setCurrentStep(0); // Changed from 1 to 0
    setQuickStep(1);
    setVideoType(null);
    setVideoSubtype(null);
    setContinuityConfig({
      enableSceneContinuity: true,
      continuityFrameIndex: -5,
      continuityReferenceWeight: 0.5,
      enableSmartContinuityJudge: true,
    });
    setUserScript('');
    setPolishedScript('');
    setCharacters([]);
    setScenes([]);
    setQuickScenes([]);
    setVideoUrl('');
    setVideoMetadata(null);
  };

  // Full mode handlers
  const handleStep0Complete = (
    selectedVideoType: VideoType,
    selectedVideoSubtype: VideoSubtype,
    selectedContinuityConfig: VideoContinuityConfig
  ) => {
    logger.info('MainApp', 'Step 0 completed', {
      videoType: selectedVideoType,
      videoSubtype: selectedVideoSubtype,
      continuityConfig: selectedContinuityConfig,
    });
    setVideoType(selectedVideoType);
    setVideoSubtype(selectedVideoSubtype);
    setContinuityConfig(selectedContinuityConfig);
    setCurrentStep(1);
  };

  const handleStep1Complete = (userScriptText: string, polishedScriptText: string) => {
    logger.info('MainApp', 'Step 1 completed', {
      userScriptLength: userScriptText.length,
      polishedScriptLength: polishedScriptText.length,
    });
    setUserScript(userScriptText);
    setPolishedScript(polishedScriptText);
    setCurrentStep(2);
  };

  const handleStep1Back = () => {
    logger.info('MainApp', 'Returning to Step 0 from Step 1');
    setCurrentStep(0);
  };

  const handleStep2Complete = (selectedCharacters: Character[]) => {
    logger.info('MainApp', 'Step 2 completed', {
      characterCount: selectedCharacters.length,
    });
    setCharacters(selectedCharacters);
    setCurrentStep(3);
  };

  const handleStep2Back = () => {
    logger.info('MainApp', 'Returning to Step 1 from Step 2');
    setCurrentStep(1);
  };

  const handleStep3Complete = (selectedScenes: Scene[]) => {
    logger.info('MainApp', 'Step 3 completed', {
      sceneCount: selectedScenes.length,
    });
    setScenes(selectedScenes);
    setCurrentStep(4);
  };

  const handleStep3Back = () => {
    logger.info('MainApp', 'Returning to Step 2 from Step 3');
    setCurrentStep(2);
  };

  const handleStep4Complete = (generatedVideoUrl: string, metadata: any) => {
    logger.info('MainApp', 'Step 4 completed - video generation successful', {
      videoUrl: generatedVideoUrl,
      metadata,
    });
    setVideoUrl(generatedVideoUrl);
    setVideoMetadata(metadata);
    setCurrentStep(5);
  };

  const handleStep4Cancel = () => {
    logger.warn('MainApp', 'Video generation cancelled by user');
    setCurrentStep(3);
  };

  const handleRegenerate = () => {
    logger.info('MainApp', 'User initiated regeneration - resetting to Step 0');
    setCurrentStep(0);
    setVideoType(null);
    setVideoSubtype(null);
    setContinuityConfig({
      enableSceneContinuity: true,
      continuityFrameIndex: -5,
      continuityReferenceWeight: 0.5,
      enableSmartContinuityJudge: true,
    });
    setUserScript('');
    setPolishedScript('');
    setCharacters([]);
    setScenes([]);
    setVideoUrl('');
    setVideoMetadata(null);
  };

  // Quick mode handlers
  const handleQuickStep1Complete = (uploadedScenes: QuickModeScene[]) => {
    logger.info('MainApp', 'Quick Step 1 completed', {
      sceneCount: uploadedScenes.length,
    });
    setQuickScenes(uploadedScenes);
    setQuickStep(2);
  };

  const handleQuickStep2Complete = (configuredScenes: QuickModeScene[]) => {
    logger.info('MainApp', 'Quick Step 2 completed', {
      sceneCount: configuredScenes.length,
    });
    setQuickScenes(configuredScenes);
    setQuickStep(3);
  };

  const handleQuickStep2Back = () => {
    logger.info('MainApp', 'Returning to Quick Step 1 from Quick Step 2');
    setQuickStep(1);
  };

  const handleQuickStep3Complete = (generatedVideoUrl: string, metadata: any) => {
    logger.info('MainApp', 'Quick Step 3 completed - video generation successful', {
      videoUrl: generatedVideoUrl,
      metadata,
    });
    setVideoUrl(generatedVideoUrl);
    setVideoMetadata(metadata);
    setQuickStep(4);
  };

  const handleQuickStep3Cancel = () => {
    logger.warn('MainApp', 'Quick mode video generation cancelled by user');
    setQuickStep(2);
  };

  const handleQuickRegenerate = () => {
    logger.info('MainApp', 'User initiated quick mode regeneration - resetting to Quick Step 1');
    setQuickStep(1);
    setQuickScenes([]);
    setVideoUrl('');
    setVideoMetadata(null);
  };

  return (
    <main className="min-h-screen bg-background flex flex-col">
      <Header />

      <div className="flex-1 flex">
        {/* Sidebar */}
        <div className="w-16 flex-shrink-0">
          <ModeSidebar
            currentMode={generationMode}
            onModeChange={handleModeChange}
          />
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden flex flex-col items-center justify-start p-6">
          {generationMode === 'full' ? (
            // Full Mode Workflow
            <StepContainer currentStep={currentStep} totalSteps={6}>
              {currentStep === 0 && (
                <Step0VideoTypeSelection
                  onNext={handleStep0Complete}
                  initialVideoType={videoType || undefined}
                  initialVideoSubtype={videoSubtype || undefined}
                  initialContinuityConfig={continuityConfig}
                />
              )}

              {currentStep === 1 && (
                <Step1ScriptInput
                  onNext={handleStep1Complete}
                  onBack={handleStep1Back}
                  initialUserScript={userScript}
                  initialPolishedScript={polishedScript}
                  videoType={videoType || undefined}
                  videoSubtype={videoSubtype || undefined}
                />
              )}

              {currentStep === 2 && (
                <Step2CharacterImages
                  polishedScript={polishedScript}
                  videoType={videoType || undefined}
                  videoSubtype={videoSubtype || undefined}
                  onNext={handleStep2Complete}
                  onBack={handleStep2Back}
                  initialCharacters={characters}
                />
              )}

              {currentStep === 3 && (
                <Step3SceneImages
                  polishedScript={polishedScript}
                  onNext={handleStep3Complete}
                  onBack={handleStep3Back}
                  initialScenes={scenes}
                />
              )}

              {currentStep === 4 && (
                <Step4VideoProgress
                  polishedScript={polishedScript}
                  characters={characters}
                  scenes={scenes}
                  videoType={videoType || undefined}
                  videoSubtype={videoSubtype || undefined}
                  continuityConfig={continuityConfig}
                  onComplete={handleStep4Complete}
                  onCancel={handleStep4Cancel}
                />
              )}

              {currentStep === 5 && (
                <Step5ResultPreview
                  videoUrl={videoUrl}
                  videoMetadata={videoMetadata}
                  onRegenerate={handleRegenerate}
                />
              )}
            </StepContainer>
          ) : (
            // Quick Mode Workflow
            <StepContainer currentStep={quickStep} totalSteps={4}>
              {quickStep === 1 && (
                <QuickStep1ImageUpload
                  onNext={handleQuickStep1Complete}
                  initialScenes={quickScenes}
                />
              )}

              {quickStep === 2 && (
                <QuickStep2SceneConfig
                  scenes={quickScenes}
                  onNext={handleQuickStep2Complete}
                  onBack={handleQuickStep2Back}
                />
              )}

              {quickStep === 3 && (
                <Step4VideoProgress
                  polishedScript="" // Not used in quick mode
                  characters={[]} // Not used in quick mode
                  scenes={[]} // Not used in quick mode
                  quickModeScenes={quickScenes}
                  onComplete={handleQuickStep3Complete}
                  onCancel={handleQuickStep3Cancel}
                  isQuickMode={true}
                />
              )}

              {quickStep === 4 && (
                <Step5ResultPreview
                  videoUrl={videoUrl}
                  videoMetadata={videoMetadata}
                  onRegenerate={handleQuickRegenerate}
                />
              )}
            </StepContainer>
          )}
        </div>
      </div>
    </main>
  );
}

