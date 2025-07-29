/**
 * Firebase Functions with GITHUB_TOKEN secret binding
 */

const { setGlobalOptions } = require("firebase-functions");
const { onRequest } = require("firebase-functions/v2/https");
const logger = require("firebase-functions/logger");
const admin = require("firebase-admin");

admin.initializeApp();
const db = admin.firestore();

// Global settings
setGlobalOptions({ maxInstances: 10 });

/**
 * Trigger experiment function
 * Requires GITHUB_TOKEN secret
 */
exports.triggerExperiment = onRequest({
  cors: true,
  maxInstances: 10,
  secrets: ["GITHUB_TOKEN"], // <-- BIND THE SECRET
}, async (request, response) => {
  // Enable CORS
  response.set('Access-Control-Allow-Origin', '*');
  response.set('Access-Control-Allow-Methods', 'GET, POST');
  response.set('Access-Control-Allow-Headers', 'Content-Type');

  if (request.method === 'OPTIONS') {
    response.status(204).send('');
    return;
  }

  if (request.method !== 'POST') {
    response.status(405).json({ error: 'Method not allowed' });
    return;
  }

  try {
    const { repository } = request.body;

    if (!repository) {
      response.status(400).json({ error: 'Repository is required' });
      return;
    }

    const experimentId = `experiment-${Date.now()}`;

    const experimentData = {
      id: experimentId,
      repository,
      status: 'created',
      variants: [],
      created_at: admin.firestore.FieldValue.serverTimestamp(),
      updated_at: admin.firestore.FieldValue.serverTimestamp()
    };

    await db.collection('experiments').doc(experimentId).set(experimentData);

    logger.info('Experiment session created in Firestore', { experimentId, repository });

    // Initialize variables
    let rlAction = null;
    let extraBuildArgs = '';

    // Generate RL action for this experiment
    try {
      const rlAgentUrl = process.env.RL_AGENT_URL || 'https://rl-agent-428721187836.us-central1.run.app';
      const actionResponse = await fetch(`${rlAgentUrl}/get-action`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          experiment_id: experimentId
        })
      });

      if (actionResponse.ok) {
        rlAction = await actionResponse.json();
        logger.info('RL action generated', { experimentId, rlAction });
        
        // Update experiment with RL action
        await db.collection('experiments').doc(experimentId).update({
          rl_action: rlAction,
          updated_at: admin.firestore.FieldValue.serverTimestamp()
        });
        
        // Use RL action parameters in workflow inputs
        extraBuildArgs = `--max-workers ${rlAction.max_workers} -Dorg.gradle.jvmargs="-Xmx${rlAction.gradle_heap_gb}g" -Dkotlin.compiler.jvmTarget=17 -Dkotlin.compiler.jvmArgs="-Xmx${rlAction.kotlin_heap_gb}g"`;
      } else {
        logger.warn('Failed to get RL action, using default parameters', { experimentId });
      }
    } catch (error) {
      logger.error('Error calling RL agent', { experimentId, error: error.message });
    }

    // Prepare GitHub Actions workflow inputs
    const workflowInputs = {
      repository: repository,
      experiment_id: experimentId,
      rl_actions: JSON.stringify(rlAction || {}),
      task: ':help', // Default task, could be made configurable
      iterations: '10',
      mode: 'dependencies cache',
      java_args: '{javaVersionVariantA:\'17\',javaVersionVariantB:\'17\',javaVendorVariantA:\'zulu\',javaVendorVariantB:\'zulu\'}',
      extra_build_args: extraBuildArgs ? `{extraArgsVariantA:'${extraBuildArgs}',extraArgsVariantB:' '}` : '{extraArgsVariantA:\' \',extraArgsVariantB:\' \'}',
      extra_report_args: '{deploy_results:\'false\',experiment_title:\'\', open_ai_request:\'true\', report_enabled:\'true\',tasktype_report:\'true\',taskpath_report:\'true\',kotlin_build_report:\'false\',process_report:\'false\',resource_usage_report:\'true\',gc_report:\'false\',only_cacheable_outcome:\'false\',threshold_task_duration:\'1000\'}',
      variant: 'main'
    };

    // Check environment variables
    console.log('Environment variables:', {
      GITHUB_TOKEN: process.env.GITHUB_TOKEN ? 'SET' : 'NOT SET',
      FIREBASE_CONFIG: process.env.FIREBASE_CONFIG ? 'SET' : 'NOT SET'
    });

    // Get GitHub token
    const githubToken = process.env.GITHUB_TOKEN;
    console.log('GitHub token found:', githubToken ? 'YES' : 'NO');

    if (!githubToken) {
      throw new Error('GitHub token is required. Ensure GITHUB_TOKEN is added as a secret.');
    }

    // Trigger GitHub Actions workflow in the current repository
    const workflowResponse = await fetch(
      `https://api.github.com/repos/cdsap/RLGradleBuilds/actions/workflows/run.yaml/dispatches`,
      {
        method: 'POST',
        headers: {
          'Authorization': `token ${githubToken}`,
          'Accept': 'application/vnd.github.v3+json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ref: 'main',
          inputs: workflowInputs
        })
      }
    );

    if (!workflowResponse.ok) {
      const errorText = await workflowResponse.text();
      logger.error('GitHub API error:', errorText);
      throw new Error(`Failed to trigger workflow: ${workflowResponse.status} ${workflowResponse.statusText}`);
    }

    logger.info('Experiment triggered successfully', {
      experimentId,
      repository,
      workflowInputs
    });

    response.json({
      success: true,
      experiment_id: experimentId,
      message: `Experiment started for ${repository}`,
      workflow_inputs: workflowInputs
    });

  } catch (error) {
    logger.error('Error triggering experiment:', error);
    response.status(500).json({
      error: 'Failed to trigger experiment',
      details: error.message
    });
  }
});

/**
 * Get experiment data
 */
exports.getExperimentData = onRequest({
  cors: true,
  maxInstances: 10
}, async (request, response) => {
  response.set('Access-Control-Allow-Origin', '*');
  if (request.method !== 'GET') {
    response.status(405).json({ error: 'Method not allowed' });
    return;
  }

  try {
    const { experiment_id } = request.query;
    if (!experiment_id) {
      response.status(400).json({ error: 'experiment_id is required' });
      return;
    }

    const experimentDoc = await db.collection('experiments').doc(experiment_id).get();
    if (!experimentDoc.exists) {
      response.status(404).json({ error: 'Experiment not found' });
      return;
    }

    response.json({
      success: true,
      experiment: experimentDoc.data()
    });

  } catch (error) {
    logger.error('Error getting experiment:', error);
    response.status(500).json({ error: 'Failed to get experiment', details: error.message });
  }
});

/**
 * Get all experiments
 */
exports.getAllExperiments = onRequest({
  cors: true,
  maxInstances: 10
}, async (request, response) => {
  response.set('Access-Control-Allow-Origin', '*');
  if (request.method !== 'GET') {
    response.status(405).json({ error: 'Method not allowed' });
    return;
  }

  try {
    const experimentsSnapshot = await db.collection('experiments').orderBy('created_at', 'desc').get();
    
    const experiments = [];
    experimentsSnapshot.forEach(doc => {
      const data = doc.data();
      // Format the experiment data for the UI
      const experiment = {
        id: doc.id,
        repository: data.repository,
        status: data.status,
        rl_action: data.rl_action,
        best_action: data.best_action,
        reward: data.reward,
        variants: data.variants || [],
        created_at: data.created_at,
        updated_at: data.updated_at
      };
      experiments.push(experiment);
    });

    response.json({
      success: true,
      experiments: experiments
    });

  } catch (error) {
    logger.error('Error getting all experiments:', error);
    response.status(500).json({ error: 'Failed to get experiments', details: error.message });
  }
});

/**
 * Update experiment status and send feedback to RL agent
 */
exports.updateExperimentStatusData = onRequest({
  cors: true,
  maxInstances: 10,
  secrets: ["GITHUB_TOKEN"], // <-- BIND THE SECRET
}, async (request, response) => {
  response.set('Access-Control-Allow-Origin', '*');
  if (request.method !== 'POST') {
    response.status(405).json({ error: 'Method not allowed' });
    return;
  }

  try {
    const { experiment_id, status, metrics, workflow_run_id, build_time, gradle_gc_time, kotlin_gc_time, kotlin_compile_duration } = request.body;
    
    logger.info('Received experiment update request', { 
      experiment_id, 
      status, 
      has_workflow_run_id: !!workflow_run_id,
      has_metrics: !!(build_time && gradle_gc_time && kotlin_gc_time)
    });
    
    if (!experiment_id) {
      response.status(400).json({ error: 'experiment_id is required' });
      return;
    }

    const updateData = {
      status: status || 'updated',
      updated_at: admin.firestore.FieldValue.serverTimestamp()
    };

    if (metrics) updateData.metrics = metrics;
    if (workflow_run_id) updateData.workflow_run_id = workflow_run_id;

    await db.collection('experiments').doc(experiment_id).update(updateData);

    logger.info('Experiment status updated', { experiment_id, status, workflow_run_id });

    // Send feedback to RL agent if we have performance metrics
    logger.info('Checking if we have metrics for continuous learning', { 
      experiment_id, 
      build_time: !!build_time, 
      gradle_gc_time: !!gradle_gc_time, 
      kotlin_gc_time: !!kotlin_gc_time,
      build_time_value: build_time,
      gradle_gc_time_value: gradle_gc_time,
      kotlin_gc_time_value: kotlin_gc_time
    });
    
    if (build_time !== undefined && gradle_gc_time !== undefined && kotlin_gc_time !== undefined) {
      try {
        const rlAgentUrl = process.env.RL_AGENT_URL || 'https://rl-agent-428721187836.us-central1.run.app';
        const feedbackResponse = await fetch(`${rlAgentUrl}/send-feedback`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            experiment_id: experiment_id,
            build_time: build_time,
            gradle_gc_time: gradle_gc_time,
            kotlin_gc_time: kotlin_gc_time,
            kotlin_compile_duration: kotlin_compile_duration
          })
        });

        if (feedbackResponse.ok) {
          const feedbackResult = await feedbackResponse.json();
          logger.info('Feedback sent to RL agent', { experiment_id, feedbackResult });
          
          // Store the best action and reward from the RL agent
          if (feedbackResult.best_action && feedbackResult.calculated_reward !== undefined) {
            // Get the current RL action from the experiment document
            const experimentDoc = await db.collection('experiments').doc(experiment_id).get();
            const experimentData = experimentDoc.data();
            const currentRlAction = experimentData.rl_action;
            
            if (!currentRlAction) {
              logger.error('No current RL action found in experiment', { experiment_id });
              return;
            }
            
            // Create variant data for this action
            const variantData = {
              variant_id: `W${currentRlAction.max_workers}_G${currentRlAction.gradle_heap_gb}_K${currentRlAction.kotlin_heap_gb}`,
              rl_action: currentRlAction,
              reward: feedbackResult.calculated_reward,
              metrics: {
                build_time: build_time,
                gradle_gc_time: gradle_gc_time,
                kotlin_gc_time: kotlin_gc_time,
                kotlin_compile_duration: kotlin_compile_duration
              },
              created_at: new Date()
            };

            // Update experiment with new variant and best action
            await db.collection('experiments').doc(experiment_id).update({
              best_action: feedbackResult.best_action,
              reward: feedbackResult.calculated_reward,
              variants: admin.firestore.FieldValue.arrayUnion(variantData),
              updated_at: admin.firestore.FieldValue.serverTimestamp()
            });
            logger.info('Stored variant and best action', { experiment_id, variant: variantData.variant_id, reward: feedbackResult.calculated_reward });
          }
          
          // Always trigger next action for continuous learning
          try {
            const experimentDoc = await db.collection('experiments').doc(experiment_id).get();
            if (experimentDoc.exists) {
              const experimentData = experimentDoc.data();
              const repository = experimentData.repository;
              
              logger.info('Scheduling next action for same experiment', { experiment_id, repository });
              
              // Generate next RL action for the same experiment
              const rlAgentUrl = process.env.RL_AGENT_URL || 'https://rl-agent-428721187836.us-central1.run.app';
              logger.info('Calling RL agent for next action', { experiment_id, rlAgentUrl });
              
              const actionResponse = await fetch(`${rlAgentUrl}/get-action`, {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  experiment_id: experiment_id
                })
              });
              
              if (actionResponse.ok) {
                const rlAction = await actionResponse.json();
                logger.info('Next RL action generated for same experiment', { experiment_id, rlAction });
                
                // Validate the RL action has required fields
                if (!rlAction || !rlAction.max_workers || !rlAction.gradle_heap_gb || !rlAction.kotlin_heap_gb) {
                  logger.error('Invalid RL action received', { experiment_id, rlAction });
                  return;
                }
                
                // Update experiment with new RL action
                await db.collection('experiments').doc(experiment_id).update({
                  rl_action: rlAction,
                  status: 'running',
                  updated_at: admin.firestore.FieldValue.serverTimestamp()
                });
                
                // Prepare workflow inputs for next action
                const extraBuildArgs = `--max-workers ${rlAction.max_workers} -Dorg.gradle.jvmargs="-Xmx${rlAction.gradle_heap_gb}g" -Dkotlin.compiler.jvmTarget=17 -Dkotlin.compiler.jvmArgs="-Xmx${rlAction.kotlin_heap_gb}g"`;
                
                const workflowInputs = {
                  repository: repository,
                  experiment_id: experiment_id,
                  rl_actions: JSON.stringify(rlAction),
                  task: ':help',
                  iterations: '10',
                  mode: 'dependencies cache',
                  java_args: '{javaVersionVariantA:\'17\',javaVersionVariantB:\'17\',javaVendorVariantA:\'zulu\',javaVendorVariantB:\'zulu\'}',
                  extra_build_args: `{extraArgsVariantA:'${extraBuildArgs}',extraArgsVariantB:' '}`,
                  extra_report_args: '{deploy_results:\'false\',experiment_title:\'\', open_ai_request:\'true\', report_enabled:\'true\',tasktype_report:\'true\',taskpath_report:\'true\',kotlin_build_report:\'false\',process_report:\'false\',resource_usage_report:\'true\',gc_report:\'false\',only_cacheable_outcome:\'false\',threshold_task_duration:\'1000\'}',
                  variant: 'main'
                };
                
                // Trigger next action for the same experiment
                const githubToken = process.env.GITHUB_TOKEN;
                logger.info('About to trigger GitHub workflow', { experiment_id, hasToken: !!githubToken });
                
                if (githubToken) {
                  logger.info('Making GitHub API call', { experiment_id, workflowInputs });
                  
                  const workflowResponse = await fetch(
                    `https://api.github.com/repos/cdsap/RLGradleBuilds/actions/workflows/run.yaml/dispatches`,
                    {
                      method: 'POST',
                      headers: {
                        'Authorization': `token ${githubToken}`,
                        'Accept': 'application/vnd.github.v3+json',
                        'Content-Type': 'application/json',
                      },
                      body: JSON.stringify({
                        ref: 'main',
                        inputs: workflowInputs
                      })
                    }
                  );
                  
                  logger.info('GitHub API response received', { experiment_id, status: workflowResponse.status, ok: workflowResponse.ok });
                  
                  if (workflowResponse.ok) {
                    logger.info('Next action triggered successfully for same experiment', { experiment_id, repository });
                  } else {
                    const errorText = await workflowResponse.text();
                    logger.error('Failed to trigger next action', { experiment_id, status: workflowResponse.status, error: errorText });
                  }
                } else {
                  logger.error('No GitHub token available', { experiment_id });
                }
              } else {
                const errorText = await actionResponse.text();
                logger.error('Failed to get RL action', { experiment_id, status: actionResponse.status, error: errorText });
              }
            }
          } catch (error) {
            logger.error('Error scheduling next action', { experiment_id, error: error.message });
          }
        } else {
          logger.warn('Failed to send feedback to RL agent', { experiment_id });
        }
      } catch (error) {
        logger.error('Error sending feedback to RL agent', { experiment_id, error: error.message });
      }
    }

    response.json({ success: true, message: 'Experiment status updated' });

  } catch (error) {
    logger.error('Error updating experiment status:', error);
    response.status(500).json({ error: 'Failed to update experiment status', details: error.message });
  }
});
