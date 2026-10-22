import React from 'react';

interface StepContainerProps {
  currentStep: number;
  totalSteps: number;
  children: React.ReactNode;
}

export const StepContainer: React.FC<StepContainerProps> = ({
  currentStep,
  children,
}) => {
  const steps = [
    { number: 1, title: 'Script Input', description: 'Enter and polish your script' },
    { number: 2, title: 'Characters', description: 'Generate character images' },
    { number: 3, title: 'Scenes', description: 'Generate scene images' },
    { number: 4, title: 'Generation', description: 'Video generation progress' },
    { number: 5, title: 'Preview', description: 'Download your video' },
  ];

  return (
    <div className="container mx-auto px-4 py-6 max-w-6xl">
      {/* Step Indicator */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          {steps.map((step, index) => (
            <React.Fragment key={step.number}>
              {/* Step Circle */}
              <div className="flex flex-col items-center flex-1">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold transition-apple ${
                    step.number < currentStep
                      ? 'bg-success text-[#0A0A0B]'
                      : step.number === currentStep
                      ? 'bg-[#EDEDF0] text-[#0A0A0B] shadow-apple-sm'
                      : 'bg-surface-hover text-text-tertiary border border-hairline'
                  }`}
                >
                  {step.number < currentStep ? (
                    <svg
                      className="w-5 h-5"
                      fill="currentColor"
                      viewBox="0 0 20 20"
                    >
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    step.number
                  )}
                </div>
                <p
                  className={`mt-2 text-xs font-medium text-center ${
                    step.number === currentStep
                      ? 'text-text-primary'
                      : 'text-text-secondary'
                  }`}
                >
                  {step.title}
                </p>
                <p className="text-xs text-text-tertiary text-center hidden sm:block">
                  {step.description}
                </p>
              </div>

              {/* Connector Line */}
              {index < steps.length - 1 && (
                <div
                  className={`flex-1 h-1 mx-2 transition-apple ${
                    step.number < currentStep
                      ? 'bg-success'
                      : 'bg-surface-hover'
                  }`}
                  style={{ maxWidth: '80px' }}
                />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Step Content */}
      <div className="fade-in">{children}</div>
    </div>
  );
};

export default StepContainer;

