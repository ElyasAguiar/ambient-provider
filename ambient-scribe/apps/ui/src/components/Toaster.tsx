
/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

// Simple placeholder toaster - in a real app you'd use something like react-hot-toast
export function Toaster() {
  return (
    <div 
      id="toast-container" 
      className="fixed top-4 right-4 z-50 space-y-2"
    >
      {/* Toast notifications will be rendered here */}
    </div>
  )
}

// Toast utility functions (simplified version)
export const toast = {
  success: (message: string) => {
    console.log('Success:', message)
    // In a real implementation, this would add a toast to the container
  },
  error: (message: string) => {
    console.error('Error:', message)
    // In a real implementation, this would add an error toast
  },
  info: (message: string) => {
    console.log('Info:', message)
    // In a real implementation, this would add an info toast
  }
}
