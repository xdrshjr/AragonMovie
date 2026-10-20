'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Card, Button, ProgressBar, LogViewer, LoadingAnimation } from '@/components/ui';
import { apiClient } from '@/lib/api';
import { logger } from '@/lib/logger';
import { Scene, Character, LogEntry, TaskStatusResponse, APIException, QuickModeScene } from '@/lib/types';
import { VideoType, VideoSubtype } from '@/lib/types/videoTypes';

interface Step4VideoProgressProps {
  polishedScript: string;
  characters: Character[];
  scenes: Scene[];
  videoType?: VideoType;
  videoSubtype?: VideoSubtype;
  onComplete: (videoUrl: string, metadata: any) => void;
  onCancel: () => void;
  quickModeScenes?: QuickModeScene[];
  isQuickMode?: boolean;
  /** Reserved for future use; currently ignored by this step */
  continuityConfig?: unknown;
}

export const Step4VideoProgress: React.FC<Step4VideoProgressProps> = ({
  polishedScript,
  characters,
  scenes,
  videoType,
  videoSubtype,
  onComplete,
  onCancel,
  quickModeScenes = [],
  isQuickMode = false,
}) => {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<string>('pending');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [currentStage, setCurrentStage] = useState('Initializing');
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<any>(null);
  const [showErrorDetails, setShowErrorDetails] = useState(false);

  // Use ref to prevent double execution in React StrictMode
  const hasStartedRef = useRef(false);

  const addLog = (level: LogEntry['level'], component: string, message: string, data?: any) => {
    const logEntry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      component,
      message,
      data,
    };
    setLogs((prev) => [...prev, logEntry]);
    logger[level]('Step4VideoProgress', message, data);
  };

  useEffect(() => {
    // Start video generation when component mounts (only once)
    // Use ref to prevent double execution in React 18 StrictMode
    if (!hasStartedRef.current) {
      hasStartedRef.current = true;
      if (isQuickMode) {
        startQuickModeGeneration();
      } else {
        startWorkflowGeneration();
      }
    }
  }, []); // Empty dependency array - only run on mount

  const startQuickModeGeneration = async () => {
    addLog('info', 'QuickModeGeneration', 'Starting quick mode video generation');

    try {
      // Prepare scenes for API
      const apiScenes = quickModeScenes.map((scene) => ({
        scene_id: scene.id,
        image: scene.imageBase64,
        duration: scene.duration,
        prompt: scene.prompt || undefined,
        camera_motion: scene.cameraMotion || undefined,
        motion_strength: scene.motionStrength,
      }));

      addLog('info', 'QuickModeGeneration',
        `Submitting ${apiScenes.length} scenes for video generation`
      );
      setCurrentStage('Submitting Quick Mode Workflow');

      // Call quick mode API
      const response = await apiClient.startQuickModeWorkflow({
        mode: 'quick',
        scenes: apiScenes,
        config: {
          video_fps: 30,
          video_resolution: '1920x1080',
          add_transitions: true,
        },
      });

      setTaskId(response.task_id);
      addLog('info', 'QuickModeGeneration', `Quick mode task submitted successfully, task_id: ${response.task_id}`);

      // Start polling
      pollTaskStatus(response.task_id, true);
    } catch (err) {
      addLog('error', 'QuickModeGeneration', 'Failed to start quick mode generation', err);

      let errorMessage = 'An unexpected error occurred';
      let details = null;

      if (err instanceof APIException) {
        errorMessage = `Failed to start quick mode: ${err.message}`;
        details = {
          code: err.code,
          details: err.details,
          retryable: err.retryable
        };
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }

      setError(errorMessage);
      setErrorDetails(details);
      setStatus('failed');
    }
  };

  const startWorkflowGeneration = async () => {
    addLog('info', 'WorkflowGeneration', 'Starting full workflow generation pipeline');
    
    try {
      // Clean the script - remove markdown code blocks if present
      let cleanedScript = polishedScript.trim();
      const codeBlockMatch = cleanedScript.match(/^```(?:yaml|yml)?\s*\n([\s\S]*?)\n```$/);
      if (codeBlockMatch) {
        cleanedScript = codeBlockMatch[1].trim();
        addLog('debug', 'WorkflowGeneration', 'Stripped markdown code blocks from script');
      }

      // Prepare character images mapping
      const characterImages: Record<string, string> = {};
      for (const char of characters) {
        if (char.selectedImage) {
          characterImages[char.name] = char.selectedImage;
          addLog('debug', 'WorkflowGeneration', `Using character image for ${char.name}`);
        }
      }

      // Prepare scene images mapping
      const sceneImages: Record<string, string> = {};
      for (const scene of scenes) {
        if (scene.selectedImage) {
          sceneImages[scene.id] = scene.selectedImage;
          addLog('debug', 'WorkflowGeneration', `Using scene image for ${scene.id}`);
        }
      }

      addLog('info', 'WorkflowGeneration', 
        `Starting workflow with ${Object.keys(characterImages).length} character images and ${Object.keys(sceneImages).length} scene images`
      );
      setCurrentStage('Submitting Workflow');

      // Call workflow API with cleaned script
      const response = await apiClient.startWorkflow({
        script: cleanedScript,
        video_type: videoType,
        video_subtype: videoSubtype,
        character_images: Object.keys(characterImages).length > 0 ? characterImages : undefined,
        scene_images: Object.keys(sceneImages).length > 0 ? sceneImages : undefined,
        config: {
          video_fps: 30,
          video_duration: 5.0,
          image_width: 1920,
          image_height: 1080,
          add_transitions: true,
          add_subtitles: false,
          enable_character_references: true,
          video_motion_strength: 0.5,
          max_concurrent_requests: 3,
        },
      });

      setTaskId(response.task_id);
      addLog('info', 'WorkflowGeneration', `Workflow task submitted successfully, task_id: ${response.task_id}`);

      // Start polling
      pollTaskStatus(response.task_id, false);
    } catch (err) {
      addLog('error', 'WorkflowGeneration', 'Failed to start workflow generation', err);

      let errorMessage = 'An unexpected error occurred';
      let details = null;

      if (err instanceof APIException) {
        errorMessage = `Failed to start workflow: ${err.message}`;
        details = {
          code: err.code,
          details: err.details,
          retryable: err.retryable
        };
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }

      setError(errorMessage);
      setErrorDetails(details);
      setStatus('failed');
    }
  };

  const pollTaskStatus = async (taskId: string, isQuickMode: boolean = false) => {
    try {
      // pollTaskUntilComplete resolves with the final (completed) status, so no
      // second getTaskStatus() call is needed here. That extra call used the
      // default 60s timeout and could surface a spurious TIMEOUT/"Generation
      // failed" even though the task had already finished successfully.
      const finalStatus = await apiClient.pollTaskUntilComplete(
        taskId,
        (statusUpdate: TaskStatusResponse) => {
          setProgress(statusUpdate.progress);
          setStatus(statusUpdate.status);

          // Update stage based on progress and mode
          if (isQuickMode) {
            // Quick mode stages
            if (statusUpdate.progress < 10) {
              setCurrentStage('Preparing Images');
            } else if (statusUpdate.progress < 70) {
              setCurrentStage('Generating Videos from Images');
            } else if (statusUpdate.progress < 95) {
              setCurrentStage('Composing Final Video');
            } else {
              setCurrentStage('Finalizing');
            }
          } else {
            // Full mode stages
            if (statusUpdate.progress < 10) {
              setCurrentStage('Initializing Project');
            } else if (statusUpdate.progress < 20) {
              setCurrentStage('Parsing Script');
            } else if (statusUpdate.progress < 40) {
              setCurrentStage('Processing Character References');
            } else if (statusUpdate.progress < 60) {
              setCurrentStage('Generating Scene Images');
            } else if (statusUpdate.progress < 85) {
              setCurrentStage('Generating Scene Videos');
            } else if (statusUpdate.progress < 98) {
              setCurrentStage('Composing Final Video');
            } else {
              setCurrentStage('Finalizing');
            }
          }

          addLog(
            'info',
            'WorkflowGeneration',
            `Progress: ${statusUpdate.progress}% - ${currentStage}`
          );
        },
        14400000 // 4 hours max (for very long video generation)
      );

      // Result comes from the resolved poll status (see above)
      if (finalStatus.status === 'completed' && finalStatus.result) {
        const workflowResult = finalStatus.result;
        
        addLog('info', 'WorkflowGeneration', 'Workflow completed successfully', {
          videoUrl: workflowResult.video_url,
          duration: workflowResult.duration,
          sceneCount: workflowResult.scene_count,
          characterCount: workflowResult.character_count,
        });
        
        // Pass result to parent
        onComplete(workflowResult.video_url, {
          duration: workflowResult.duration,
          sceneCount: workflowResult.scene_count,
          characterCount: workflowResult.character_count,
          assets: workflowResult.assets,
        });
      } else {
        throw new Error('Workflow completed but no result found');
      }
    } catch (err) {
      addLog('error', 'WorkflowGeneration', 'Workflow generation failed', err);

      let errorMessage = 'An unexpected error occurred';
      let details = null;

      if (err instanceof APIException) {
        errorMessage = `Workflow failed: ${err.message}`;
        details = {
          code: err.code,
          details: err.details,
          retryable: err.retryable
        };
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }

      setError(errorMessage);
      setErrorDetails(details);
      setStatus('failed');
    }
  };

  const handleCancel = async () => {
    if (taskId) {
      addLog('warn', 'WorkflowGeneration', 'User requested cancellation');
      
      try {
        await apiClient.cancelTask(taskId);
        addLog('info', 'WorkflowGeneration', 'Task cancelled successfully');
        setStatus('cancelled');
        onCancel();
      } catch (err) {
        addLog('error', 'WorkflowGeneration', 'Failed to cancel task', err);
      }
    } else {
      onCancel();
    }
  };



  return (
    <div className="space-y-6">
      {/* Progress Section */}
      <Card title="Video Generation Progress">
        <div className="space-y-6">
          {/* Progress Bar */}
          <ProgressBar
            progress={progress}
            label="Overall Progress"
            showPercentage={true}
            color={error ? 'red' : status === 'completed' ? 'green' : 'blue'}
          />

          {/* Current Stage */}
          <div className="text-center">
            <p className="text-apple-body text-text-secondary mb-2">Current Stage:</p>
            <p className="text-apple-headline text-text-primary font-semibold">{currentStage}</p>
          </div>

          {/* Status Message */}
          <div className="text-center">
            {status === 'processing' && (
              <LoadingAnimation message={`${currentStage}...`} />
            )}
            {status === 'completed' && (
              <p className="text-apple-green text-apple-headline">
                ✓ Video generation completed!
              </p>
            )}
            {status === 'failed' && error && (
              <p className="text-apple-red text-apple-headline">
                ✗ Generation failed
              </p>
            )}
          </div>

          {/* Cancel Button */}
          {(status === 'pending' || status === 'processing') && (
            <div className="flex justify-center">
              <Button variant="danger" onClick={handleCancel}>
                Cancel Generation
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Logs Section */}
      <Card title="Generation Logs">
        <LogViewer logs={logs} maxHeight="500px" autoScroll={true} />
      </Card>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-apple-red rounded-apple-md p-4">
          <h4 className="text-apple-red font-semibold mb-2">Error</h4>
          <p className="text-apple-red text-sm mb-3">{error}</p>

          {/* Error Details */}
          {errorDetails && (
            <div className="mt-3">
              <button
                onClick={() => setShowErrorDetails(!showErrorDetails)}
                className="text-apple-red text-sm underline hover:no-underline focus:outline-none"
              >
                {showErrorDetails ? '▼ Hide Details' : '▶ Show Details'}
              </button>

              {showErrorDetails && (
                <div className="mt-3 p-3 bg-white dark:bg-gray-800 rounded border border-gray-300 dark:border-gray-600">
                  <div className="space-y-2 text-sm font-mono">
                    {errorDetails.code && (
                      <div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Error Code:</span>{' '}
                        <span className="text-gray-900 dark:text-gray-100">{errorDetails.code}</span>
                      </div>
                    )}

                    {errorDetails.details?.service && (
                      <div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Service:</span>{' '}
                        <span className="text-gray-900 dark:text-gray-100">{errorDetails.details.service}</span>
                      </div>
                    )}

                    {errorDetails.details?.stage && (
                      <div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Stage:</span>{' '}
                        <span className="text-gray-900 dark:text-gray-100">{errorDetails.details.stage}</span>
                      </div>
                    )}

                    {errorDetails.details?.error_type && (
                      <div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Error Type:</span>{' '}
                        <span className="text-gray-900 dark:text-gray-100">{errorDetails.details.error_type}</span>
                      </div>
                    )}

                    {errorDetails.details?.error_code && (
                      <div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">API Error Code:</span>{' '}
                        <span className="text-gray-900 dark:text-gray-100">{errorDetails.details.error_code}</span>
                      </div>
                    )}

                    {errorDetails.retryable !== undefined && (
                      <div>
                        <span className="font-semibold text-gray-700 dark:text-gray-300">Retryable:</span>{' '}
                        <span className={errorDetails.retryable ? 'text-green-600' : 'text-red-600'}>
                          {errorDetails.retryable ? 'Yes' : 'No'}
                        </span>
                      </div>
                    )}

                    {errorDetails.details?.api_response && (
                      <div className="mt-3">
                        <span className="font-semibold text-gray-700 dark:text-gray-300">API Response:</span>
                        <pre className="mt-1 p-2 bg-gray-100 dark:bg-gray-900 rounded text-xs overflow-x-auto">
                          {JSON.stringify(errorDetails.details.api_response, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="mt-4 flex gap-2">
            <Button variant="secondary" onClick={onCancel}>
              Go Back
            </Button>
            {errorDetails?.retryable && (
              <Button
                variant="primary"
                onClick={() => {
                  setError(null);
                  setErrorDetails(null);
                  setShowErrorDetails(false);
                  setProgress(0);
                  setStatus('pending');
                  hasStartedRef.current = false;
                  if (isQuickMode) {
                    startQuickModeGeneration();
                  } else {
                    startWorkflowGeneration();
                  }
                }}
              >
                Retry
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Step4VideoProgress;
