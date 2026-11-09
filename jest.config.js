module.exports = {
  testEnvironment: 'node',
  roots: ['<rootDir>/test', '<rootDir>/lib', '<rootDir>/lambda', '<rootDir>/bin'],
  testMatch: ['**/*.test.ts'],
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
  transform: {
    '^.+\\.tsx?$': 'ts-jest'
  },
  setupFilesAfterEnv: ['aws-cdk-lib/testhelpers/jest-autoclean'],
  collectCoverageFrom: ['lib/**/*.ts', 'lambda/**/*.ts', 'bin/**/*.ts', '!**/*.d.ts'],
  coverageProvider: 'v8',
  coverageDirectory: 'coverage/typescript',
  coverageReporters: ['text-summary', 'json', 'json-summary', 'lcov', 'html'],
  coverageThreshold: {
    global: { branches: 100, functions: 100, lines: 100, statements: 100 },
  },
};
