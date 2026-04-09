module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/apps'],
  testMatch: ['**/*.spec.ts'],
  moduleNameMapper: {
    '^@common/(.*)$': '<rootDir>/libs/common/src/$1',
  },
};
