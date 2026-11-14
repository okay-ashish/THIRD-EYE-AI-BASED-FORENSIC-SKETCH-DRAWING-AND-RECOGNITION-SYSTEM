/**
 * ThirdEye Ant Design Design System & Theme Manager
 * ==============================================================================
 * Provides:
 * 1. Ant Design SVG Icon Library and Auto-Mounting (.anticon, .anticon-*)
 * 2. Tri-state Theme Manager (System / Light / Dark) with Zero-FOUC persistence
 * 3. Dynamic background & high-contrast typography token updates
 */

(function () {
    'use strict';

    // Official Ant Design 5 SVG Icons Dictionary (1024x1024 vector paths)
    const ANT_ICONS = {
        'SunOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true" fill-rule="evenodd"><path d="M548 818v126a16 16 0 01-16 16h-40a16 16 0 01-16-16V818c15.85 1.64 27.84 2.46 36 2.46 8.15 0 20.16-.82 36-2.46m205.25-115.66l89.1 89.1a16 16 0 010 22.62l-28.29 28.29a16 16 0 01-22.62 0l-89.1-89.1c11.66-11.02 20.91-23.47 27.42-36.81 1.09-2.22 2.27-4.59 3.49-7.1m-482.5 0c1.22 2.51 2.4 4.88 3.49 7.1 6.51 13.34 15.76 25.79 27.42 36.81l-89.1 89.1a16 16 0 01-22.62 0l-28.29-28.29a16 16 0 010-22.62l89.1-89.1m47.92-225.51c0-106.87 86.63-193.5 193.5-193.5s193.5 86.63 193.5 193.5-86.63 193.5-193.5 193.5-193.5-86.63-193.5-193.5zm-112.5 0c0-8.15.82-20.16 2.46-36H82a16 16 0 00-16 16v40a16 16 0 0016 16h125.63c-1.64-15.85-2.46-27.84-2.46-36zm741.7 0c0 8.16-.82 20.15-2.46 36H942a16 16 0 0016-16v-40a16 16 0 00-16-16H819.17c1.64 15.84 2.46 27.85 2.46 36zM725.68 287.52l89.1-89.1a16 16 0 000-22.62l-28.29-28.29a16 16 0 00-22.62 0l-89.1 89.1c11.02 11.66 23.47 20.91 36.81 27.42 2.22 1.09 4.59 2.27 7.1 3.49m-427.36 0c2.51-1.22 4.88-2.4 7.1-3.49 13.34-6.51 25.79-15.76 36.81-27.42l-89.1-89.1a16 16 0 00-22.62 0L202.22 175.8a16 16 0 000 22.62l89.1 89.1zM548 206V80a16 16 0 00-16-16h-40a16 16 0 00-16 16v126c15.85-1.64 27.84-2.46 36-2.46 8.15 0 20.16.82 36 2.46z"></path></svg>',
        'MoonOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true" fill-rule="evenodd"><path d="M489.5 111.66c30.65-1.8 45.98 36.44 22.58 56.33A243.35 243.35 0 00426 354c0 134.76 109.24 244 244 244 72.58 0 139.9-31.83 186.01-86.08 19.87-23.38 58.07-8.1 56.34 22.53C898.39 747.88 729.08 912 519.84 912c-225.33 0-408-182.67-408-408 0-218.47 172.5-393.7 377.66-392.34z"></path></svg>',
        'DesktopOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M928 140H96c-17.7 0-32 14.3-32 32v496c0 17.7 14.3 32 32 32h380v112H304c-8.8 0-16 7.2-16 16v48c0 4.4 3.6 8 8 8h432c4.4 0 8-3.6 8-8v-48c0-8.8-7.2-16-16-16H548V700h380c17.7 0 32-14.3 32-32V172c0-17.7-14.3-32-32-32zm-40 488H136V212h752v416z"></path></svg>',
        'HomeOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M946.5 505L560.1 118.8l-25.9-25.9a31.5 31.5 0 00-44.4 0L77.5 505a63.9 63.9 0 00-18.8 45.4c0 35.2 28.7 64 64 64h42.5V856c0 17.7 14.3 32 32 32h160c17.7 0 32-14.3 32-32V640h160v216c0 17.7 14.3 32 32 32h160c17.7 0 32-14.3 32-32V614.4h42.5c35.3 0 64-28.7 64-64 0-17.1-6.8-33.3-18.7-45.4zM858 542.4h-48.4c-9.1 0-17.7 3.8-23.8 10.4l-1.3 1.4V816H668.5V592c0-17.7-14.3-32-32-32h-224c-17.7 0-32 14.3-32 32v224H264V554.2l-1.3-1.4c-6.1-6.6-14.7-10.4-23.8-10.4H190.5L512 232.2 833.5 542.4H858z"></path></svg>',
        'FileTextOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M854.6 288.6L639.4 73.4c-6-6-14.1-9.4-22.6-9.4H192c-17.7 0-32 14.3-32 32v832c0 17.7 14.3 32 32 32h640c17.7 0 32-14.3 32-32V311.3c0-8.6-3.4-16.7-9.4-22.7zM602 137.8L790.2 326H602V137.8zM792 888H232V128h314v220c0 17.7 14.3 32 32 32h214v508z"></path><path d="M328 448h368c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8zm0 160h368c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8zm0 160h208c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8z"></path></svg>',
        'FolderOpenOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M928 444H820V330.4c0-16.8-6.8-33-18.8-45L709.6 194c-12-12-28.2-18.8-45-18.8H104c-22.1 0-40 17.9-40 40v664c0 22.1 17.9 40 40 40h784c22.1 0 40-17.9 40-40V444zm-796-72V243.2h532.7l83.3 83.3V372H132zm728 472H132V444h728v400zm-76-248h-72v-72c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v72h-72c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h72v72c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8v-72h72c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"></path></svg>',
        'SettingOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M924.8 615.9l-82.5-47.6c-4.8-2.8-10.7-3.1-15.8-.8l-40.6 18.2c-5.1 2.3-9 6.7-10.7 12.1-10.8 33.6-28.2 64.3-51.1 90.9-3.7 4.3-5.2 10.1-4.2 15.6l7.8 43.7c1 5.6-.9 11.2-5 15.1l-60.6 57.5c-4.1 3.9-9.8 5.6-15.3 4.6l-43.7-7.8c-5.6-1-11.3.5-15.6 4.2-26.6 22.9-57.3 40.3-90.9 51.1-5.4 1.7-9.8 5.6-12.1 10.7l-18.2 40.6c-2.3 5.1-2 11 .8 15.8l47.6 82.5c4.6 7.9 2.5 17.9-4.8 23.3l-68.5 50.8c-7.3 5.4-17.4 4.5-23.7-2.1l-60.1-62.8c-4.1-4.3-10-6.4-15.8-5.8l-44.2 4.4c-5.6.6-10.8 3.5-14.1 8.1-20.7 28.7-47.5 52.8-78.9 71-5 2.9-8.4 7.8-9.3 13.5l-6.8 43.9c-.9 5.6-4.5 10.3-9.7 12.7l-77.9 35.8c-5.2 2.4-11.3 1.9-16.1-1.3l-37.5-25c-4.7-3.1-10.6-4.1-16.1-2.6-34.7 9.4-71.1 11.6-107.1 6.5-5.6-.8-11.2 1.1-15.3 5.1l-31.9 31.2c-4.1 4-9.8 5.9-15.4 5.2l-83.6-10.5c-5.6-.7-10.4-4.1-12.9-9.1l-20.2-39.6c-2.6-5.1-1.9-11.2 1.8-15.7l28.6-34.9c3.7-4.5 4.8-10.6 3.2-16.2-10.4-34.4-13.4-70.5-8.8-106.3.7-5.6-1.5-11.2-5.9-15.1l-34.5-30.8c-4.4-3.9-6.7-9.7-6.2-15.5l7.5-83.9c.5-5.6 3.6-10.6 8.5-13.3l38.8-21.7c5-2.8 8.4-7.8 9.2-13.5 5.5-35.7 18.2-69.8 37.3-100.5 3-4.8 3.6-10.7 1.6-16l-15.3-41.8c-2-5.4-1-11.4 2.6-15.9l54.3-67.9c3.6-4.5 9.2-7.1 15-6.9l44.4 1.5c5.6.2 11.1-2.2 14.8-6.4 23.3-26.6 52-47.8 84.4-62.3 5.2-2.3 8.9-6.9 10.2-12.5l9.9-43.3c1.3-5.5 5.2-10 10.6-12l78.7-29.6c5.4-2 11.4-1.1 16 2.5l36.1 27.6c4.6 3.5 10.6 4.7 16.2 3.3 35.1-8.7 71.7-10.1 107.6-4.1 5.6.9 11.2-.8 15.4-4.7l32.7-30.4c4.2-3.9 9.9-5.7 15.5-4.8l83.4 13.5c5.6.9 10.3 4.5 12.6 9.6l18.5 40.5c2.3 5.1 1.5 11.1-2.2 15.5l-29.4 34.3c-3.8 4.4-5 10.5-3.4 16.1 11.2 34.1 15.1 70.1 11.6 106-.5 5.6 1.5 11.2 5.8 15.1l35.1 31.4c4.4 3.9 6.7 9.7 6.2 15.5l-7.5 83.9c-.5 5.6-3.6 10.6-8.5 13.3zm-412.8-103.9c-88.4 0-160 71.6-160 160s71.6 160 160 160 160-71.6 160-160-71.6-160-160-160z"></path></svg>',
        'UserOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M858.5 763.6a374 374 0 00-80.6-119.5 375.63 375.63 0 00-119.5-80.6c-.4-.2-.8-.3-1.2-.5C719.5 518 760 444.7 760 362c0-137-111-248-248-248S264 225 264 362c0 82.7 40.5 156 102.8 201.1-.4.2-.8.3-1.2.5-44.1 20.5-84.4 47.7-119.5 80.6a374 374 0 00-80.6 119.5A371.7 371.7 0 00136 864c0 4.4 3.6 8 8 8h60c4.4 0 8-3.6 8-8 0-165.7 134.3-300 300-300s300 134.3 300 300c0 4.4 3.6 8 8 8h60c4.4 0 8-3.6 8-8 0-35.3-9.9-69.2-27.5-100.4zM512 538c-97.2 0-176-78.8-176-176s78.8-176 176-176 176 78.8 176 176-78.8 176-176 176z"></path></svg>',
        'LockOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M632 440h-16V304c0-57.3-46.7-104-104-104s-104 46.7-104 104v136h-16c-17.7 0-32 14.3-32 32v352c0 17.7 14.3 32 32 32h240c17.7 0 32-14.3 32-32V472c0-17.7-14.3-32-32-32zM480 304c0-17.7 14.3-32 32-32s32 14.3 32 32v136H480V304zm160 488H384V512h256v280z"></path></svg>',
        'LogoutOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M868 732h-72c-4.4 0-8 3.6-8 8v160H236V124h552v160c0 4.4 3.6 8 8 8h72c4.4 0 8-3.6 8-8V84c0-22.1-17.9-40-40-40H196c-22.1 0-40 17.9-40 40v856c0 22.1 17.9 40 40 40h632c22.1 0 40-17.9 40-40V740c0-4.4-3.6-8-8-8z"></path><path d="M497.6 626.6l152-152c6.2-6.2 6.2-16.4 0-22.6l-152-152c-6.2-6.2-16.4-6.2-22.6 0l-22.6 22.6c-6.2 6.2-6.2 16.4 0 22.6L577.8 468H288c-8.8 0-16 7.2-16 16v32c0 8.8 7.2 16 16 16h289.8L475 604c-6.2 6.2-6.2 16.4 0 22.6l22.6 22.6c6.2 6.2 16.4 6.2 22.6 0z"></path></svg>',
        'MenuOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M904 160H120c-4.4 0-8 3.6-8 8v64c0 4.4 3.6 8 8 8h784c4.4 0 8-3.6 8-8v-64c0-4.4-3.6-8-8-8zm0 624H120c-4.4 0-8 3.6-8 8v64c0 4.4 3.6 8 8 8h784c4.4 0 8-3.6 8-8v-64c0-4.4-3.6-8-8-8zm0-312H120c-4.4 0-8 3.6-8 8v64c0 4.4 3.6 8 8 8h784c4.4 0 8-3.6 8-8v-64c0-4.4-3.6-8-8-8z"></path></svg>',
        'EyeOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M942.2 486.2C847.4 286.5 704.1 186 512 186c-192.1 0-335.4 100.5-430.2 300.2a60.3 60.3 0 000 51.6C176.6 737.5 319.9 838 512 838c192.1 0 335.4-100.5 430.2-300.2 7.7-16.2 7.7-35 0-51.6zM512 766c-161.3 0-279.4-81.8-362.7-254C232.6 339.8 350.7 258 512 258c161.3 0 279.4 81.8 362.7 254C791.4 684.2 673.3 766 512 766zm-4-438c-101.6 0-184 82.4-184 184s82.4 184 184 184 184-82.4 184-184-82.4-184-184-184zm0 296c-61.9 0-112-50.1-112-112s50.1-112 112-112 112 50.1 112 112-50.1 112-112 112z"></path></svg>',
        'CheckCircleOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.5l-256 256a15.99 15.99 0 01-22.6 0l-128-128a16 16 0 010-22.6l22.6-22.6a16 16 0 0122.6 0L438 565.4l244.9-244.9a16 16 0 0122.6 0l22.6 22.6a16 16 0 010 22.6z"></path></svg>',
        'CloseOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true" fill-rule="evenodd"><path d="M799.86 166.31c.02 0 .04.02.08.06l57.69 57.7c.04.03.05.05.06.08a16 16 0 010 22.62L569.93 512l287.76 287.23a16 16 0 010 22.62l-57.69 57.7a16 16 0 01-22.62 0L489.62 592.32l-287.7 287.23a16 16 0 01-22.62 0l-57.69-57.7a16 16 0 010-22.62L409.31 512 121.61 224.77a16 16 0 010-22.62l57.69-57.7a16 16 0 0122.62 0l287.7 287.23 287.62-287.23a16 16 0 0122.62 0z"></path></svg>',
        'ExclamationCircleOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm-32 232c0-4.4 3.6-8 8-8h48c4.4 0 8 3.6 8 8v288c0 4.4-3.6 8-8 8h-48c-4.4 0-8-3.6-8-8V296zm32 464c-26.5 0-48-21.5-48-48s21.5-48 48-48 48 21.5 48 48-21.5 48-48 48z"></path></svg>',
        'BulbOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M632 758H392c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h240c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8zm-32 104H424c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h176c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8zm-88-814C333.7 48 189 192.7 189 371c0 85.3 33 163 87.2 220.8 33.3 35.5 56.4 79.5 67 126.2h137.6c10.6-46.7 33.7-90.7 67-126.2C602 534 635 456.3 635 371c0-178.3-144.7-323-323-323zm108.6 517.9c-27.1 28.9-46.7 64-58.1 102.1H373.5c-11.4-38.1-31-73.2-58.1-102.1A253.22 253.22 0 01257 371c0-140.8 114.2-255 255-255s255 114.2 255 255c0 70.8-28.7 137.8-77.4 186.9z"></path></svg>',
        'FormOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M904 512h-56c-4.4 0-8 3.6-8 8v320H184V184h320c4.4 0 8-3.6 8-8v-56c0-4.4-3.6-8-8-8H144c-17.7 0-32 14.3-32 32v736c0 17.7 14.3 32 32 32h736c17.7 0 32-14.3 32-32V520c0-4.4-3.6-8-8-8z"></path><path d="M355.9 534.9L304 688.1c-2.4 7.1.6 15 7.1 17.4 2.2.8 4.6 1 6.9.5l153.2-51.9c4.2-1.4 7.9-4 10.7-7.4l411.3-488.7c5.6-6.7 4.7-16.7-2-22.3l-102.1-85.7c-6.7-5.6-16.7-4.7-22.3 2L355.9 534.9zm43.5 125.6l23.5-69.5 46 38.6-69.5 30.9zm101.4-82.7l-46-38.6 348.6-414 46 38.6-348.6 414z"></path></svg>',
        'PlusOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M482 152h60c4.4 0 8 3.6 8 8v704c0 4.4-3.6 8-8 8h-60c-4.4 0-8-3.6-8-8V160c0-4.4 3.6-8 8-8z"></path><path d="M160 482h704c4.4 0 8 3.6 8 8v60c0 4.4-3.6 8-8 8H160c-4.4 0-8-3.6-8-8v-60c0-4.4 3.6-8 8-8z"></path></svg>',
        'SearchOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M909.6 854.5L649.9 594.8C690.2 542.7 712 479 712 412c0-80.2-31.3-155.4-87.9-212.1-56.6-56.7-132-87.9-212.1-87.9s-155.5 31.3-212.1 87.9C143.2 256.5 112 331.8 112 412c0 80.1 31.3 155.5 87.9 212.1C256.5 680.8 331.8 712 412 712c67 0 130.6-21.8 182.7-62l259.7 259.6a8.2 8.2 0 0011.6 0l43.6-43.5c3.2-3.2 3.2-8.4 0-11.6zM412 636c-123.7 0-224-100.3-224-224s100.3-224 224-224 224 100.3 224 224-100.3 224-224 224z"></path></svg>',
        'CameraOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M864 260H728l-32.4-90.8a32.07 32.07 0 00-30.2-21.2H358.6c-13.5 0-25.6 8.5-30.1 21.2L296 260H160c-44.2 0-80 35.8-80 80v456c0 44.2 35.8 80 80 80h704c44.2 0 80-35.8 80-80V340c0-44.2-35.8-80-80-80zm8 536c0 4.4-3.6 8-8 8H160c-4.4 0-8-3.6-8-8V340c0-4.4 3.6-8 8-8h153.2c13.5 0 25.6-8.5 30.1-21.2L376 220h272l32.7 90.8c4.5 12.7 16.7 21.2 30.1 21.2H864c4.4 0 8 3.6 8 8v456zM512 384c-88.4 0-160 71.6-160 160s71.6 160 160 160 160-71.6 160-160-71.6-160-160-160zm0 256c-53 0-96-43-96-96s43-96 96-96 96 43 96 96-43 96-96 96z"></path></svg>',
        'SafetyCertificateOutlined': '<svg viewBox="64 64 896 896" width="1em" height="1em" fill="currentColor" focusable="false" aria-hidden="true"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372zm-73.4-319.4L337.8 563.8a16 16 0 010-22.6l22.6-22.6a16 16 0 0122.6 0l79.9 79.9 164.7-164.7a16 16 0 0122.6 0l22.6 22.6a16 16 0 010 22.6L461.2 664.6a16 16 0 01-22.6 0z"></path></svg>'
    };

    // Classname to Icon mapping for standard Ant Design classes
    const CLASS_MAP = {
        'anticon-sun': 'SunOutlined',
        'anticon-moon': 'MoonOutlined',
        'anticon-desktop': 'DesktopOutlined',
        'anticon-home': 'HomeOutlined',
        'anticon-file-text': 'FileTextOutlined',
        'anticon-form': 'FormOutlined',
        'anticon-folder-open': 'FolderOpenOutlined',
        'anticon-setting': 'SettingOutlined',
        'anticon-user': 'UserOutlined',
        'anticon-lock': 'LockOutlined',
        'anticon-logout': 'LogoutOutlined',
        'anticon-menu': 'MenuOutlined',
        'anticon-eye': 'EyeOutlined',
        'anticon-check-circle': 'CheckCircleOutlined',
        'anticon-close': 'CloseOutlined',
        'anticon-exclamation-circle': 'ExclamationCircleOutlined',
        'anticon-bulb': 'BulbOutlined',
        'anticon-plus': 'PlusOutlined',
        'anticon-search': 'SearchOutlined',
        'anticon-camera': 'CameraOutlined',
        'anticon-safety': 'SafetyCertificateOutlined'
    };

    /**
     * Mounts SVG icons into .anticon containers
     */
    function mountAntIcons(root = document) {
        // Elements with data-ant-icon attribute
        const customElements = root.querySelectorAll('[data-ant-icon]');
        customElements.forEach(el => {
            const iconName = el.getAttribute('data-ant-icon');
            if (iconName && ANT_ICONS[iconName] && !el.hasChildNodes()) {
                el.innerHTML = ANT_ICONS[iconName];
            }
        });

        // Elements with anticon and class mapping
        const classElements = root.querySelectorAll('.anticon');
        classElements.forEach(el => {
            if (el.hasChildNodes()) return; // Already rendered inline
            for (const [cls, iconName] of Object.entries(CLASS_MAP)) {
                if (el.classList.contains(cls) && ANT_ICONS[iconName]) {
                    el.innerHTML = ANT_ICONS[iconName];
                    break;
                }
            }
        });
    }

    /**
     * Resolves effective theme: 'light' or 'dark'
     */
    function resolveTheme(mode) {
        if (mode === 'system') {
            const darkMatches = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
            return darkMatches ? 'dark' : 'light';
        }
        return mode === 'light' ? 'light' : 'dark';
    }

    /**
     * Applies theme mode to document and updates segmented buttons
     */
    function applyTheme(mode, persist = true) {
        const root = document.documentElement;
        const resolved = resolveTheme(mode);

        root.setAttribute('data-theme', mode);
        root.setAttribute('data-resolved-theme', resolved);

        if (persist) {
            try {
                localStorage.setItem('thirdeye_theme_mode', mode);
            } catch (err) {
                console.warn('Could not persist theme:', err);
            }
        }

        // Update segmented toggle buttons
        const segmented = document.getElementById('themeSegmentedControl');
        if (segmented) {
            const buttons = segmented.querySelectorAll('.ant-theme-btn');
            buttons.forEach(btn => {
                const btnMode = btn.getAttribute('data-theme-mode');
                const isActive = (btnMode === mode);
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        }

        // Dispatch custom theme change event for dynamic charts or canvas if needed
        window.dispatchEvent(new CustomEvent('thirdeye:themechange', {
            detail: { mode, resolved }
        }));
    }

    /**
     * Initializes theme toggle control and listeners
     */
    function initThemeManager() {
        let initialMode = 'system';
        try {
            initialMode = localStorage.getItem('thirdeye_theme_mode') || 'system';
        } catch (e) {
            initialMode = 'system';
        }

        applyTheme(initialMode, false);

        // Listen for OS system theme changes
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            const handleMediaChange = () => {
                const currentMode = document.documentElement.getAttribute('data-theme') || 'system';
                if (currentMode === 'system') {
                    applyTheme('system', false);
                }
            };
            if (mediaQuery.addEventListener) {
                mediaQuery.addEventListener('change', handleMediaChange);
            } else if (mediaQuery.addListener) {
                mediaQuery.addListener(handleMediaChange);
            }
        }

        // Attach click handlers to theme toggle buttons
        const segmented = document.getElementById('themeSegmentedControl');
        if (segmented) {
            segmented.addEventListener('click', (e) => {
                const btn = e.target.closest('.ant-theme-btn');
                if (!btn) return;
                const newMode = btn.getAttribute('data-theme-mode');
                if (newMode) {
                    applyTheme(newMode, true);
                }
            });
        }

        // Mount Ant Design Icons
        mountAntIcons(document);
    }

    // Expose API on window.ThirdEyeTheme
    window.ThirdEyeTheme = {
        mountIcons: mountAntIcons,
        setTheme: applyTheme,
        getTheme: () => document.documentElement.getAttribute('data-theme') || 'system',
        getResolvedTheme: () => document.documentElement.getAttribute('data-resolved-theme') || 'dark',
        icons: ANT_ICONS
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initThemeManager);
    } else {
        initThemeManager();
    }
})();

